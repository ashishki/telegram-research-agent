"""Read-only PRM archive-refresh orchestration receipts.

This module never starts ingestion, reaction sync, vector work, enrichment, a
timer, or a canonical write. It renders supplied/dry-run component outcomes so
the operator can see independent failure domains before approving any routine.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping


REFRESH_RECEIPT_SCHEMA_VERSION = "prm_refresh_receipt.v1"
_STATUSES = {"not_run", "ok", "failed", "stale", "blocked", "partial", "no_new_data", "unknown"}
_COMPONENTS = ("archive", "reactions", "vector", "enrichment")
_REASON_CODES = {"", "not_approved", "credentials_unavailable", "component_failed", "stale_index"}


def build_refresh_receipt(components: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Normalize independent component results without retaining raw content."""

    supplied = components or {}
    result: dict[str, dict[str, str | int]] = {}
    for name in _COMPONENTS:
        item = supplied.get(name) if isinstance(supplied.get(name), Mapping) else {}
        status = str(item.get("status") or "not_run")
        if status not in _STATUSES:
            raise ValueError(f"unsupported refresh status for {name}")
        result[name] = {
            "status": status,
            "updated_at": str(item.get("updated_at") or ""),
            "count": max(0, int(item.get("count") or 0)),
            "reason": _safe_reason_code(item.get("reason")),
        }
    return {
        "schema_version": REFRESH_RECEIPT_SCHEMA_VERSION,
        "dry_run": True,
        "components": result,
        "write_performed": False,
        "schedule_changed": False,
        "provider_egress": False,
    }


def build_archive_health_receipt(db_path: str | Path) -> dict[str, Any]:
    """Project archive coverage from SQLite in read-only mode.

    This deliberately reports coverage separately from a refresh attempt: the
    canonical DB has no durable attempt ledger, so a status request must not
    invent one or substitute its own current timestamp.
    """

    path = Path(db_path)
    archive: dict[str, Any] = {
        "status": "unknown",
        "count": 0,
        "updated_at": "",
        "reason": "not_approved",
        "last_attempt": "unknown",
        "last_success": "unknown",
    }
    if not path.exists():
        archive.update({"status": "failed", "reason": "component_failed"})
        return build_refresh_receipt({"archive": archive})
    try:
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
            row = connection.execute("SELECT count(*), max(posted_at) FROM posts").fetchone()
    except (OSError, sqlite3.Error):
        archive.update({"status": "failed", "reason": "component_failed"})
    else:
        count, coverage_at = int(row[0] or 0), str(row[1] or "")
        archive.update(
            {
                "status": "no_new_data" if count else "stale",
                "count": count,
                "updated_at": coverage_at,
                "reason": "" if count else "stale_index",
                "coverage_at": coverage_at,
            }
        )
    receipt = build_refresh_receipt({"archive": archive})
    receipt["archive_health"] = {
        "coverage_at": str(archive.get("coverage_at") or ""),
        "last_attempt": "unknown",
        "last_success": "unknown",
        "status_read_only": True,
    }
    return receipt


def render_refresh_receipt(receipt: Mapping[str, Any]) -> str:
    """Render a compact Russian owner view with one line per failure domain."""

    if receipt.get("schema_version") != REFRESH_RECEIPT_SCHEMA_VERSION:
        raise ValueError("unsupported refresh receipt schema")
    components = receipt.get("components") if isinstance(receipt.get("components"), Mapping) else {}
    labels = {"archive": "Архив", "reactions": "Реакции", "vector": "Векторный индекс", "enrichment": "Обогащение"}
    status_labels = {"not_run": "не запускалось", "ok": "готово", "failed": "ошибка", "stale": "устарело", "blocked": "заблокировано", "partial": "частично", "no_new_data": "новых данных нет", "unknown": "неизвестно"}
    lines = ["Статус обновления (dry-run)"]
    for name in _COMPONENTS:
        item = components.get(name) if isinstance(components.get(name), Mapping) else {}
        status = str(item.get("status") or "not_run")
        suffix = str(item.get("reason") or "").strip()
        lines.append(f"{labels[name]}: {status_labels.get(status, 'неизвестно')}{f' — {suffix}' if suffix else ''}")
    lines.extend(
        [
            "",
            "Ничего не запускалось: архив, реакции, индекс и обогащение независимы.",
            "Для реального обновления нужны отдельные утверждённые параметры и явное подтверждение записи.",
        ]
    )
    health = receipt.get("archive_health") if isinstance(receipt.get("archive_health"), Mapping) else {}
    if health:
        coverage_at = str(health.get("coverage_at") or "неизвестно")
        lines.insert(1, f"Покрытие архива до: {coverage_at}; последняя попытка: неизвестно")
    return "\n".join(lines)


def build_operator_refresh_receipt(refresh_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Keep the approved archive-refresh CLI projection backward-compatible."""

    before = _mapping(refresh_payload.get("before"))
    after = _mapping(refresh_payload.get("after"))
    privacy = _mapping(refresh_payload.get("privacy"))
    return {
        "schema_version": "prm_operator_refresh_receipt.v1",
        "status": str(refresh_payload.get("status") or "failed"),
        "new_posts": max(0, int(after.get("posts") or 0) - int(before.get("posts") or 0)),
        "channels_touched": int(refresh_payload.get("channels_touched") or 0),
        "latest_posted_at": str(after.get("max_posted_at") or ""),
        "reaction_summary": {"status": "not_run"},
        "enrichment": {"status": "not_run"},
        "boundaries": {
            "report_generation": False,
            "provider_egress": bool(privacy.get("provider_egress")),
            "migrations_run": bool(privacy.get("migrations_run")),
            "reaction_sync": bool(privacy.get("reaction_sync")),
            "vector_rebuild": bool(privacy.get("local_vector_sidecar_write")),
            "dogfood_evidence": bool(privacy.get("dogfood_evidence")),
            "release_claim": bool(privacy.get("release_claim")),
        },
    }


def build_refresh_failure_receipt() -> dict[str, Any]:
    """Keep an observable safe failure receipt for the approved CLI path."""

    return build_operator_refresh_receipt({"status": "failed", "before": {}, "after": {}, "privacy": {}})


def _safe_reason_code(value: object) -> str:
    code = str(value or "").strip().casefold()
    return code if code in _REASON_CODES else "component_failed"


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
