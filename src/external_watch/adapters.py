"""UTD source adapters for Localist and minimized public HTML surfaces."""
from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from typing import Any, Mapping


class AdapterError(ValueError):
    pass


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        clean = " ".join(data.split())
        if clean:
            self.parts.append(clean)


def _names(values: Any) -> list[str]:
    result = []
    for value in values or []:
        if isinstance(value, Mapping) and value.get("name"):
            result.append(str(value["name"]))
    return result


def parse_localist(body: bytes) -> list[dict[str, Any]]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterError("invalid Localist JSON") from exc
    if not isinstance(payload, Mapping) or not isinstance(payload.get("events"), list):
        raise AdapterError("Localist schema drift: events[] missing")
    items: list[dict[str, Any]] = []
    for wrapper in payload["events"]:
        event = wrapper.get("event") if isinstance(wrapper, Mapping) else None
        if not isinstance(event, Mapping) or event.get("id") is None:
            raise AdapterError("Localist schema drift: event.id missing")
        instances = []
        for raw in event.get("event_instances") or []:
            inst = raw.get("event_instance") if isinstance(raw, Mapping) else None
            if not isinstance(inst, Mapping) or inst.get("id") is None or not inst.get("start"):
                continue
            instances.append({"id": str(inst["id"]), "start": str(inst["start"]), "end": str(inst.get("end") or ""), "all_day": bool(inst.get("all_day"))})
        filters = event.get("filters") if isinstance(event.get("filters"), Mapping) else {}
        base = {
            "event_id": str(event["id"]),
            "title": str(event.get("title") or "").strip(),
            "url": str(event.get("url") or "").strip(),
            "status": str(event.get("status") or "unknown").lower(),
            "updated_at": str(event.get("updated_at") or ""),
            "instances": instances,
            "audiences": _names(filters.get("event_target_audience")),
            "topics": _names(filters.get("event_topic")),
            "event_types": _names(filters.get("event_types")),
            "departments": _names(event.get("departments")),
        }
        if not instances:
            items.append({**base, "item_key": f"event:{base['event_id']}"})
        else:
            for inst in instances:
                items.append({**base, "instance": inst, "item_key": f"event:{base['event_id']}:instance:{inst['id']}"})
    return items


def parse_html_document(body: bytes, *, source: str, canonical_url: str) -> list[dict[str, Any]]:
    parser = _TextParser()
    parser.feed(body.decode("utf-8", "replace"))
    text = "\n".join(parser.parts)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email removed]", text)
    text = re.sub(r"\b(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b", "[phone removed]", text)
    selected = ("f-1", "f1", "j-1", "j1", "international", "immigration", "employment", "deadline", "orientation", "status") if source == "isso" else ("resource", "eligible", "eligibility", "international student", "financial", "food", "housing", "clothing", "government benefits")
    lines = []
    for line in text.splitlines():
        low = line.casefold()
        if any(token in low for token in selected):
            lines.append(line[:600])
    material = "\n".join(lines[:120])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return [{"item_key": f"document:{source}", "source": source, "canonical_url": canonical_url, "material_text": material, "material_hash": digest, "line_count": min(len(lines), 120)}]


def canonical_hash(item: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
