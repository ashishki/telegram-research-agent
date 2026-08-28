#!/usr/bin/env python3
"""One-shot public UTD source capture for UTD-2 evidence.

Allowlisted public HTTPS only. Produces minimized sanitized JSON fixtures. No
cookies, credentials, Telegram data, provider calls, DB writes or delivery.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib import request

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "utd-capture")
OUT.mkdir(parents=True, exist_ok=True)
UA = "telegram-research-agent-utd-evidence/0.1"
MAX_BYTES = 1_000_000
SAFE_HEADERS = {"content-type", "etag", "last-modified", "cache-control", "date", "expires"}

SOURCES = {
    "calendar": ("https://calendar.utdallas.edu/api/2/events?days=14&pp=10&page=1", "localist_json"),
    "isso": ("https://isso.utdallas.edu/", "html_excerpt"),
    "basic_needs": ("https://basicneeds.utdallas.edu/resource-hub/", "html_excerpt"),
}

class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]
    def handle_data(self, data):
        s=" ".join(data.split())
        if s: self.parts.append(s)


def fetch(url: str):
    req=request.Request(url, headers={"User-Agent":UA,"Accept":"application/json,text/html;q=0.9"})
    with request.urlopen(req, timeout=20) as r:
        if r.geturl().split('/')[2] != url.split('/')[2]:
            raise RuntimeError("cross-host redirect rejected")
        body=r.read(MAX_BYTES+1)
        if len(body)>MAX_BYTES: raise RuntimeError("response too large")
        headers={k.lower():v for k,v in r.headers.items() if k.lower() in SAFE_HEADERS}
        return r.status, r.headers.get_content_type(), headers, body


def sanitize_calendar(raw: bytes):
    payload=json.loads(raw.decode("utf-8"))
    events=[]
    for wrapper in (payload.get("events") or [])[:10]:
        e=(wrapper or {}).get("event") or {}
        events.append({
            "id":e.get("id"), "title":e.get("title"), "url":e.get("url"),
            "status":e.get("status"), "updated_at":e.get("updated_at"),
            "event_instances":e.get("event_instances") or [],
            "filters":{k:e.get("filters",{}).get(k,[]) for k in ("event_target_audience","event_topic","event_types")},
            "departments":e.get("departments") or [],
        })
    return {"page":payload.get("page") or {}, "date":payload.get("date") or {}, "events":events}


def sanitize_html(raw: bytes, source: str):
    p=Text(); p.feed(raw.decode("utf-8","replace")); text="\n".join(p.parts)
    text=re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email removed]", text)
    text=re.sub(r"\b(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b", "[phone removed]", text)
    keys = ("international", "f-1", "f1", "j-1", "j1", "deadline", "orientation", "employment", "resource", "eligib", "financial", "food", "housing", "clothing")
    lines=[x for x in text.splitlines() if any(k in x.lower() for k in keys)]
    return {"excerpt_lines":lines[:80], "excerpt_truncated":len(lines)>80}


def main():
    captured=datetime.now(timezone.utc).isoformat()
    receipt={"schema_version":"utd_capture_receipt.v1","captured_at":captured,"sources":{}}
    for source,(url,kind) in SOURCES.items():
        try:
            status,ctype,headers,raw=fetch(url)
            if status != 200: raise RuntimeError(f"HTTP {status}")
            content=sanitize_calendar(raw) if source=="calendar" else sanitize_html(raw,source)
            fixture={"schema_version":"utd_source_fixture.v1","source":source,"kind":kind,"contains_private_data":False,"sanitized":True,"canonical_url":url.split('?')[0],"captured_at":captured,"transport":{"status":status,"content_type":ctype,"headers":headers},"content":content}
            path=OUT/f"{source}.fixture.json"; path.write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            receipt["sources"][source]={"ok":True,"fixture":path.name}
        except Exception as exc:
            receipt["sources"][source]={"ok":False,"error":type(exc).__name__+": "+str(exc)}
    (OUT/"receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(receipt,ensure_ascii=False))
    return 0 if all(x["ok"] for x in receipt["sources"].values()) else 1

if __name__ == "__main__": raise SystemExit(main())
