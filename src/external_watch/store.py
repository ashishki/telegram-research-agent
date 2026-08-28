"""Derived sidecar SQLite state for UTD shadow polling."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_health(
 source TEXT PRIMARY KEY, status TEXT NOT NULL, checked_at TEXT NOT NULL,
 error_code TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS items(
 source TEXT NOT NULL, item_key TEXT NOT NULL, payload_hash TEXT NOT NULL,
 payload_json TEXT NOT NULL, state TEXT NOT NULL, first_seen TEXT NOT NULL,
 last_seen TEXT NOT NULL, PRIMARY KEY(source,item_key)
);
CREATE TABLE IF NOT EXISTS changes(
 id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, item_key TEXT NOT NULL,
 change_type TEXT NOT NULL, observed_at TEXT NOT NULL, payload_json TEXT NOT NULL,
 relevance_json TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ShadowStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.executescript(SCHEMA)

    def health(self, source: str, status: str, *, error_code: str | None = None, detail: str | None = None) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO source_health(source,status,checked_at,error_code,detail) VALUES(?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET status=excluded.status,checked_at=excluded.checked_at,error_code=excluded.error_code,detail=excluded.detail", (source, status, _now(), error_code, detail))
            db.commit()

    def apply_success(self, source: str, items: list[Mapping[str, Any]], hashes: Mapping[str, str], relevance: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
        now = _now()
        seen = {str(x["item_key"]) for x in items}
        changes = []
        with sqlite3.connect(self.path) as db:
            previous = {row[0]: (row[1], row[2], row[3]) for row in db.execute("SELECT item_key,payload_hash,payload_json,state FROM items WHERE source=?", (source,))}
            for item in items:
                key = str(item["item_key"])
                digest = hashes[key]
                payload = json.dumps(item, ensure_ascii=False, sort_keys=True)
                rel = dict(relevance.get(key) or {})
                old = previous.get(key)
                state = "cancelled" if str(item.get("status") or "").lower() in {"cancelled", "canceled"} else "active"
                if old is None:
                    change = "new"
                elif old[2] == "cancelled" and state == "active":
                    change = "reinstated"
                elif old[2] != "cancelled" and state == "cancelled":
                    change = "cancelled"
                elif old[0] != digest:
                    change = "updated"
                else:
                    change = "unchanged"
                db.execute("INSERT INTO items(source,item_key,payload_hash,payload_json,state,first_seen,last_seen) VALUES(?,?,?,?,?,?,?) ON CONFLICT(source,item_key) DO UPDATE SET payload_hash=excluded.payload_hash,payload_json=excluded.payload_json,state=excluded.state,last_seen=excluded.last_seen", (source, key, digest, payload, state, now, now))
                if change != "unchanged":
                    rec = {"source": source, "item_key": key, "change_type": change, "payload": dict(item), "relevance": rel}
                    changes.append(rec)
                    db.execute("INSERT INTO changes(source,item_key,change_type,observed_at,payload_json,relevance_json) VALUES(?,?,?,?,?,?)", (source, key, change, now, payload, json.dumps(rel, ensure_ascii=False, sort_keys=True)))
            for key, (_, old_payload, old_state) in previous.items():
                if key in seen or old_state == "disappeared":
                    continue
                db.execute("UPDATE items SET state='disappeared',last_seen=? WHERE source=? AND item_key=?", (now, source, key))
                rel = dict(relevance.get(key) or {})
                rec = {"source": source, "item_key": key, "change_type": "disappeared", "payload": json.loads(old_payload), "relevance": rel}
                changes.append(rec)
                db.execute("INSERT INTO changes(source,item_key,change_type,observed_at,payload_json,relevance_json) VALUES(?,?,?,?,?,?)", (source, key, "disappeared", now, old_payload, json.dumps(rel, ensure_ascii=False, sort_keys=True)))
            db.commit()
        self.health(source, "ok")
        return changes
