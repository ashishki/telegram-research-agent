#!/usr/bin/env python3
"""Profile-ranked weekly brief: widen the pool, rank by the operator profile,
draft editorial with a persona prompt, render the fixed-page PDF, optionally
send it to the owner's Telegram.

This is an operator experiment path. It reads the local archive read-only and
uses the same default-off, PA-02-typed editorial transport as
``prm.cli editorial-brief``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from prm.briefs import BriefBuildRequest, BriefWindow, CoverageSource, build_brief_document  # noqa: E402
from prm.editorial_transport import (  # noqa: E402
    build_operator_editorial_access,
    editorial_enabled,
    synthesize_opencode_editorial,
)
from prm import report_exports  # noqa: E402

DB_PATH = os.environ.get("AGENT_DB_PATH", str(PROJECT_ROOT / "data" / "agent.db"))
# Weighted interest families aligned with the operator's projects. Multi-concept
# matches dominate; generic finance/marketing terms are deliberately absent.
WEIGHTED_INTERESTS: dict[str, int] = {
    "agent runtime": 6, "agentic": 5, "agents": 3, "agent": 3, "orchestration": 5,
    "eval": 5, "evals": 5, "evaluation": 4, "benchmark": 4, "harness": 5,
    "quality gate": 4, "guardrail": 4, "approval": 3, "rag": 5, "retrieval": 5,
    "pgvector": 4, "embedding": 3, "long context": 5, "context": 3, "memory": 4,
    "tool use": 5, "tool calling": 4, "mcp": 4, "codex": 3, "claude code": 4,
    "cursor": 3, "coding agent": 5, "automation": 3, "observability": 3,
    "inference": 3, "fine-tune": 3, "open-source": 2, "opensource": 2,
    "adoption": 2, "research brief": 4, "signal analytics": 2,
}
# Russian stems (substring match) because the archive is mostly Russian.
WEIGHTED_INTERESTS_RU: dict[str, int] = {
    "агент": 4, "оркестр": 5, "оценк": 5, "бенчмарк": 4, "харнесс": 5, "память": 4,
    "контекст": 3, "инструмент": 3, "инференс": 3, "рантайм": 5, "аппрув": 3,
    "гард": 4, "внедрен": 2, "автоматизац": 3, "наблюдаем": 3, "опенсорс": 2,
    "мультимодал": 3, "ретрив": 5, "эмбеддинг": 3, "дообуч": 3, "промпт": 2,
    "рассужд": 3, "надёжн": 3, "стоимост": 2, "кэш": 2, "финтюн": 3,
}
NOISE_HINTS = (
    "розыгрыш", "скидк", "промокод", "giveaway", "плов", "мем", "шутк", "халяв",
    "казино", "букмекер", "memecoin", "nft", "криптовалют",
)
# Operator has decided these vendors are not worth following (2026-09-24).
BLOCKED_SOURCE_TERMS = ("яндекс", "yandex", "сбер", "sber", "сбербанк")
CORE_CONCEPTS = {
    "agent runtime", "agentic", "agents", "agent", "агент", "оркестр", "eval", "evals",
    "evaluation", "harness", "харнесс", "benchmark", "бенчмарк", "rag",
    "retrieval", "ретрив", "memory", "память", "orchestration", "long context",
    "tool use", "tool calling", "mcp", "runtime", "рантайм",
}


def _load_eval_module():
    spec = importlib.util.spec_from_file_location(
        "prm_product_ux_eval_for_rank", PROJECT_ROOT / "tools" / "prm_product_ux_eval.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def build_profile(db_path: str) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    projects: list[dict[str, Any]] = []
    terms: set[str] = set()
    for row in conn.execute("SELECT name,description,keywords FROM projects WHERE active=1"):
        try:
            keywords = [str(k).strip() for k in json.loads(row["keywords"] or "[]") if str(k).strip()]
        except Exception:
            keywords = []
        description = str(row["description"] or "").strip()
        if description or keywords:
            projects.append({"name": row["name"], "description": description, "keywords": keywords})
        for kw in keywords:
            if len(kw) >= 4 and re.fullmatch(r"[a-zA-Z][a-zA-Z0-9 _\-/+.]*", kw):
                terms.add(kw.casefold())
    channels: dict[str, float] = {}
    noisy: set[str] = set()
    for row in conn.execute("SELECT channel_username,channel_score,low_signal_tags FROM channel_memory"):
        channels[str(row["channel_username"])] = float(row["channel_score"] or 0.5)
        if int(row["low_signal_tags"] or 0) > 0:
            noisy.add(str(row["channel_username"]))
    conn.close()
    return {"projects": projects, "project_terms": sorted(terms), "channels": channels, "noisy": noisy}


def _match_terms(text: str, terms: list[str]) -> list[str]:
    low = text.casefold()
    hits = []
    for term in terms:
        if len(term) < 4 and term not in {"rag", "sdk", "mcp", "cli", "eval"}:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", low):
            hits.append(term)
    return sorted(set(hits))


def rank_pool(db_path: str, *, window: BriefWindow, profile: dict[str, Any]) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id,channel_username,message_id,posted_at,text,message_url FROM raw_posts "
        "WHERE posted_at>=? AND posted_at<? ORDER BY posted_at DESC",
        (window.start_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
         window.end_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")),
    ).fetchall()
    conn.close()
    weighted = {term.casefold(): weight for term, weight in WEIGHTED_INTERESTS.items()}
    project_terms = profile["project_terms"]
    channels = profile["channels"]
    noisy = profile["noisy"]
    scored: list[dict[str, Any]] = []
    for row in rows:
        text = " ".join(str(row["text"] or "").split())
        if len(text) < 40:
            continue
        low = text.casefold()
        if any(term in low for term in BLOCKED_SOURCE_TERMS):
            continue
        hits = _match_terms(text, list(weighted) + project_terms)
        ru_hits = [stem for stem in WEIGHTED_INTERESTS_RU if stem in low]
        hits = sorted(set(hits) | set(ru_hits))
        weights = sorted((weighted.get(term, 0) for term in hits), reverse=True)
        # Diminishing returns: breadth alone must not dominate depth.
        weight = sum(value * (0.55 ** index) for index, value in enumerate(weights))
        # Phrase (multi-word) matches are stronger evidence than single tokens.
        weight += 2.0 * sum(1 for term in hits if " " in term)
        has_core = any(term in CORE_CONCEPTS for term in hits)
        has_phrase = any(" " in term for term in hits)
        if has_core:
            weight += 2.0
        if not has_core and not has_phrase and len(hits) < 3:
            weight *= 0.3
        channel = str(row["channel_username"])
        channel_bonus = (channels.get(channel, 0.5) - 0.5) * 4.0
        signal = float(weight) + channel_bonus
        if any(hint in low for hint in NOISE_HINTS):
            signal -= 3.0
        if channel in noisy:
            signal -= 1.5
        if re.search(r"https?://", text):
            signal += 0.2
        if "```" in text:
            signal += 0.3
        scored.append(
            {
                "message_id": row["message_id"],
                "channel": channel,
                "posted_at": row["posted_at"],
                "text": text,
                "url": row["message_url"] or f"https://t.me/{channel.lstrip('@')}/{row['message_id']}",
                "hits": hits,
                "signal": round(signal, 3),
            }
        )
    scored.sort(key=lambda item: (-item["signal"], item["posted_at"]), reverse=False)
    return scored


def select_ranked(scored: list[dict[str, Any]], *, top: int, per_channel: int = 5) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    used: dict[str, int] = {}
    for item in sorted(scored, key=lambda i: (-i["signal"], i["posted_at"])):
        if used.get(item["channel"], 0) >= per_channel:
            continue
        chosen.append(item)
        used[item["channel"]] = used.get(item["channel"], 0) + 1
        if len(chosen) >= top:
            break
    return chosen


def build_persona(profile: dict[str, Any]) -> str:
    project_lines = []
    for project in profile["projects"][:12]:
        label = project["name"].split("/")[-1]
        detail = project["description"] or ", ".join(project["keywords"][:6])
        project_lines.append(f"- {label}: {detail[:120]}")
    preferred = sorted(profile["channels"].items(), key=lambda kv: -kv[1])[:5]
    noise = sorted(profile["noisy"])
    return (
        "Ты редактор недельного брифа для Артёма Шишкина — основателя и инженера, который строит "
        "управляемых AI-агентов и инфраструктуру оценки. Пиши как понимающий его аналитик, а не как "
        "новостную ленту.\n\n"
        "Его активные проекты и вектор:\n"
        + "\n".join(project_lines)
        + "\n\nКлючевые интересы: AI-агенты и агентный рантайм, оркестрация и approval/guardrails, "
        "evals/бенчмарки/quality gates, RAG и извлечение знаний, память и research briefs, workflow→agent, "
        "AI coding агенты (Codex/Claude Code/Cursor), автоматизация, измеримость и adoption, "
        "финансы с риск-дисциплиной, творческие системы (кино/сны).\n"
        f"Предпочитает каналы: {', '.join(ch for ch, _ in preferred)}. "
        f"Считает шумными: {', '.join(noise) if noise else '—'}.\n\n"
        "Отбирай и перерабатывай ТОЛЬКО то, что реально меняет его инструменты, архитектуру, оценки, "
        "безопасность или стратегию. Игнорируй мемы, общие новости, гаджеты и финансы без прямого "
        "применения. Не копируй посты — делай саммари с объяснением пользы. "
        "Не вставляй URL, ссылки и HTML в поля title/summary/explanation/why_selected/next_step/caveat; "
        "цитаты (quote) должны быть точными подстроками без ссылок; источники уже приложены отдельно."
    )


def _evidence_map(item: dict[str, Any], index: int) -> dict[str, Any]:
    text = re.sub(r"https?://\S+", "", item["text"])
    text = " ".join(text.split())
    first_line = text.split(".")[0]
    title = " ".join(first_line.split()) or item["channel"]
    if len(title) > 90:
        title = (title[:90].rsplit(" ", 1)[0] or title[:90]) + "…"
    return {
        "local_archive_provenance": True,
        "evidence_id": f"evidence_rank_{index:02d}",
        "source_url": item["url"],
        "title": title,
        "support_span": text[:1200],
        "posted_at": item["posted_at"],
        "topics": tuple(item["hits"][:8]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default="AI и research за неделю")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--per-channel", type=int, default=5)
    parser.add_argument("--out-dir", type=Path, default=PROJECT_ROOT / ".playbook-artifacts/profile_brief")
    parser.add_argument("--model", default="mimo-v2.6-pro")
    parser.add_argument("--provider-timeout", type=int, default=150)
    parser.add_argument("--attempts", type=int, default=4)
    parser.add_argument("--consent", default="")
    parser.add_argument("--send", action="store_true")
    parser.add_argument(
        "--send-consent",
        default="",
        help="Required with --send; must be the exact literal 'send-to-owner-telegram'.",
    )
    parser.add_argument("--dump-ranked", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    now = datetime.now(timezone.utc)
    window = BriefWindow.from_iso(
        timezone_name="UTC",
        start_at=(now - timedelta(days=args.days)).isoformat(),
        end_at=now.isoformat(),
        generated_at=now.isoformat(),
    )
    profile = build_profile(DB_PATH)
    scored = rank_pool(DB_PATH, window=window, profile=profile)
    chosen = select_ranked(scored, top=max(1, args.top), per_channel=max(1, args.per_channel))
    if args.dump_ranked:
        print(json.dumps(
            [{"ch": c["channel"], "mid": c["message_id"], "signal": c["signal"], "hits": c["hits"],
              "head": c["text"][:90]} for c in chosen], ensure_ascii=False, indent=1))
    request = BriefBuildRequest(
        topic=str(args.question),
        window=window,
        evidence=tuple(_evidence_map(item, i) for i, item in enumerate(chosen, start=1)),
        coverage=(CoverageSource("local_archive_selected_evidence", "partial"),),
        limitations=("profile_ranked_local_selection", "full_archive_coverage_not_measured"),
    )
    document = build_brief_document(request)

    editorial_meta: dict[str, Any] = {"status": "skipped"}
    if not editorial_enabled():
        editorial_meta = {"status": "disabled"}
    elif not args.consent:
        editorial_meta = {"status": "authorization_required"}
    else:
        access = build_operator_editorial_access(
            owner_ref="owner_profile_brief",
            connection_ref="connection_profile_brief",
            resource_ref="resource_profile_brief",
            consent=str(args.consent),
            attempts=int(args.attempts),
        )
        editorial, editorial_meta = synthesize_opencode_editorial(
            document,
            question=str(args.question),
            access=access,
            model=args.model,
            timeout=args.provider_timeout,
            attempts=args.attempts,
            persona=build_persona(profile),
        )
        if editorial is not None:
            from dataclasses import replace

            document = build_brief_document(replace(request, editorial=editorial))

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    html = report_exports.render_paginated_html(document)
    pdf = report_exports.render_paginated_pdf(document)
    (out / "brief_paginated.html").write_text(str(html.body), encoding="utf-8")
    (out / "brief_paginated.pdf").write_bytes(pdf.body)
    (out / "ranked.json").write_text(
        json.dumps([{k: v for k, v in c.items() if k != "text"} for c in chosen], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    manifest = {
        "status": "ok",
        "editorial": editorial_meta,
        "stories": len(document.editorial.stories) if document.editorial else 0,
        "candidates_in_pool": len(scored),
        "selected": [{"ch": c["channel"], "mid": c["message_id"], "signal": c["signal"], "hits": c["hits"]} for c in chosen],
        "pdf": str(out / "brief_paginated.pdf"),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"editorial": editorial_meta, "stories": manifest["stories"],
                      "pool": len(scored), "pdf": manifest["pdf"]}, ensure_ascii=False))

    if args.send and str(args.send_consent) != "send-to-owner-telegram":
        print("refused: --send requires --send-consent send-to-owner-telegram")
        args.send = False
    if args.send and (out / "brief_paginated.pdf").is_file():
        try:
            import requests

            env: dict[str, str] = {}
            env_path = PROJECT_ROOT / ".env"
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    key, value = line.split("=", 1)
                    env[key.strip()] = value.strip().strip('"').strip("'")
            token = env.get("TELEGRAM_BOT_TOKEN") or env.get("TELEGRAM_TOKEN")
            chat = env.get("TELEGRAM_OWNER_CHAT_ID")
            if token and chat:
                with (out / "brief_paginated.pdf").open("rb") as handle:
                    response = requests.post(
                        f"https://api.telegram.org/bot{token}/sendDocument",
                        data={"chat_id": chat, "caption": "Недельный бриф — переранжировано по профилю + редакторский проход"},
                        files={"document": ("brief.pdf", handle, "application/pdf")},
                        timeout=120,
                    )
                print("sent:", response.json().get("ok"))
        except Exception as error:  # pragma: no cover - env dependent
            print("send_failed:", type(error).__name__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
