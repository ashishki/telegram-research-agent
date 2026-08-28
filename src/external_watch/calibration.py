"""Feedback-derived calibration suggestions; never mutates confirmed profile."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def calibration_report(sidecar_db: str | Path) -> dict[str, Any]:
    path = Path(sidecar_db)
    with sqlite3.connect(path) as db:
        rows = list(db.execute("""
            SELECT r.source, r.payload_json, f.action
            FROM delivery_receipts r JOIN watch_feedback f USING(delivery_key)
            WHERE f.action IN ('useful','noise','more','less','mute','pause')
        """))
    by_source: dict[str, dict[str, int]] = {}
    by_category: dict[str, dict[str, int]] = {}
    for source, raw, action in rows:
        by_source.setdefault(str(source), {}).setdefault(str(action), 0)
        by_source[str(source)][str(action)] += 1
        try:
            candidate = json.loads(raw)
        except Exception:
            candidate = {}
        rel = candidate.get("relevance") if isinstance(candidate, dict) else {}
        for category in (rel.get("categories") or []) if isinstance(rel, dict) else []:
            bucket = by_category.setdefault(str(category), {})
            bucket[str(action)] = bucket.get(str(action), 0) + 1
    suggestions = []
    for source, counts in sorted(by_source.items()):
        if counts.get("noise", 0) + counts.get("less", 0) >= 3 and counts.get("useful", 0) == 0:
            suggestions.append({"kind": "source_downrank", "source": source, "reason": "3+ negative signals without useful feedback"})
    for category, counts in sorted(by_category.items()):
        if counts.get("more", 0) >= 2:
            suggestions.append({"kind": "category_upweight", "category": category, "reason": "2+ explicit more-like-this signals"})
        if counts.get("noise", 0) + counts.get("less", 0) >= 3:
            suggestions.append({"kind": "category_downweight", "category": category, "reason": "3+ negative signals"})
    return {"schema_version": "utd_calibration_report.v1", "by_source": by_source, "by_category": by_category, "suggestions": suggestions, "profile_mutated": False}
