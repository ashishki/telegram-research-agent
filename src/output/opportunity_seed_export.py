import json
import math
import os
import re
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config.settings import PROJECT_ROOT, Settings
from output.ai_report_contract import INTELLIGENCE_CONTRACT_VERSION, RADAR_INTELLIGENCE_CONTRACT_VERSION
from output.downstream_knowledge import MVP_KNOWLEDGE_ATOM_TYPES, load_downstream_knowledge_threads
from output.market_context_lens import (
    DEFAULT_BASELINE_DAYS,
    build_market_context_lens,
    market_context_lens_seed,
)
from output.reporting_period import (
    TRAILING_SEVEN_DAYS,
    ReportingPeriod,
    register_reporting_period_sqlite,
    resolve_reporting_period,
)


OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "opportunity_seeds"
MARKET_PACK_DIR = PROJECT_ROOT / "data" / "output" / "market_pain_packs"
MARKET_CONTEXT_LIMIT = 120

SURFACE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "manual_workaround",
        (
            "вручную",
            "руками",
            "копир",
            "copy",
            "spreadsheet",
            "таблиц",
            "csv",
            "export",
            "сохраня",
            "скрин",
            "перенос",
        ),
    ),
    (
        "search_intent",
        (
            "how to",
            "как ",
            "ищу",
            "что использовать",
            "alternative",
            "аналог",
            "converter",
            "конверт",
            "generator",
            "генератор",
        ),
    ),
    (
        "competitor_traction",
        (
            "pricing",
            "mrr",
            "arr",
            "product hunt",
            "launch",
            "запуск",
            "запустил",
            "конкурент",
            "платн",
            "подписк",
        ),
    ),
    (
        "repeated_questions",
        (
            "часто спраш",
            "постоянно",
            "каждый раз",
            "same question",
            "faq",
            "reddit",
            "stackoverflow",
            "stack exchange",
        ),
    ),
    (
        "creator_content_gap",
        (
            "поиск",
            "search",
            "seo",
            "индекс",
            "archive",
            "архив",
            "сайт",
            "website",
            "youtube",
            "rutube",
            "vk",
        ),
    ),
    (
        "platform_timing_event",
        (
            "api",
            "sdk",
            "model",
            "модель",
            "release",
            "обнов",
            "депрек",
            "deprecat",
            "rate limit",
            "policy",
            "terms",
            "gpt-oss",
            "anthropic",
            "openai",
            "яндекс",
        ),
    ),
    (
        "store_category_demand",
        (
            "chrome extension",
            "расширение",
            "app store",
            "marketplace",
            "plugin",
            "плагин",
            "бот",
            "extension",
        ),
    ),
    (
        "workflow_automation",
        (
            "workflow",
            "процесс",
            "оператор",
            "automation",
            "автоматиза",
            "approval",
            "sla",
            "support",
            "webhook",
            "n8n",
        ),
    ),
    (
        "education_rollout",
        (
            "обуч",
            "training",
            "rollout",
            "adoption",
            "команда",
            "курс",
            "воркшоп",
            "гайд",
        ),
    ),
)

DEMAND_QUERY_TERMS = tuple(
    sorted({pattern for _surface, patterns in SURFACE_PATTERNS for pattern in patterns})
)
CREATOR_CONTEXT_TERMS = ("telegram", "телеграм", "content", "контент", "youtube", "rutube", "vk")
CREATOR_DISCOVERY_TERMS = ("поиск", "search", "seo", "индекс", "archive", "архив", "сайт", "website")
TELEGRAM_DISCOVERY_TERMS = ("поиск", "search", "seo", "индекс", "archive", "архив")
ACTIONABLE_BUCKETS = {"strong", "watch", "cultural"}
ACTIONABLE_TAGS = {"strong", "interesting", "try_in_project", "read_later"}


@dataclass(frozen=True)
class OpportunitySeedExportResult:
    week_label: str
    output_path: str
    seed_count: int
    scanned_count: int
    knowledge_thread_count: int = 0
    knowledge_threads: list[dict] | None = None
    market_pack_path: str | None = None
    market_pain_pack: dict | None = None
    market_lens_path: str | None = None
    market_baseline_path: str | None = None
    market_delta_path: str | None = None
    market_context_lens: dict | None = None
    run_date: str = ""
    generated_at: str = ""
    reporting_week: str = ""
    period_mode: str = ""
    analysis_period_start: str = ""
    analysis_period_end: str = ""


def export_opportunity_seeds(
    settings: Settings,
    *,
    days: int | None = None,
    week_label: str | None = None,
    period_mode: str | None = None,
    reporting_period: ReportingPeriod | None = None,
    limit: int = 80,
    output_path: Path | None = None,
    include_channels: tuple[str, ...] = (),
    now: datetime | None = None,
    market_context_days: int = DEFAULT_BASELINE_DAYS,
    force_market_baseline: bool = False,
) -> OpportunitySeedExportResult:
    if reporting_period is not None:
        if days is not None or week_label is not None or period_mode is not None or now is not None:
            raise ValueError(
                "reporting_period cannot be combined with days, week_label, period_mode, or now"
            )
        period = reporting_period
    else:
        if days is not None and int(days) != 7:
            raise ValueError("rolling opportunity export supports exactly seven days")
        if days is not None and week_label is not None:
            raise ValueError("week_label cannot be combined with rolling days")
        if days is not None and period_mode is not None:
            raise ValueError("rolling --days cannot be combined with another period mode")
        resolved_mode = period_mode
        if days is not None and resolved_mode is None and week_label is None:
            resolved_mode = TRAILING_SEVEN_DAYS
        period = resolve_reporting_period(
            now,
            week_label=week_label,
            period_mode=resolved_mode,
        )
    period_fields = period.to_dict()
    period_start = period_fields["analysis_period_start"]
    period_end = period_fields["analysis_period_end"]
    clean_week = period.week_label
    target_path = output_path or OUTPUT_DIR / f"{clean_week}.json"
    normalized_channels = {_normalize_channel(channel) for channel in include_channels if channel}

    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        knowledge_threads = load_downstream_knowledge_threads(
            connection,
            atom_types=MVP_KNOWLEDGE_ATOM_TYPES,
            min_atom_last_seen_at=period_start,
            max_atom_last_seen_at=period_end,
            limit=max(1, min(limit, 20)),
        )
        rows = _fetch_recent_posts(
            connection,
            period_start,
            period_end,
            scan_limit=max(limit * 8, 300),
        )
    market_lens = build_market_context_lens(
        settings,
        reporting_period=period,
        baseline_days=max(1, market_context_days),
        delta_days=max(
            1,
            math.ceil(
                (period.analysis_period_end - period.analysis_period_start).total_seconds()
                / 86_400
            ),
        ),
        output_root=_market_lens_output_root_for(target_path),
        force_baseline=force_market_baseline,
    )
    market_pack = market_lens.baseline_pack

    seeds = [_seed_from_knowledge_thread(thread) for thread in knowledge_threads]
    for row in rows:
        if len(seeds) >= limit:
            break
        surfaces = classify_demand_surfaces(str(row["content"] or ""))
        manual_tags = _split_csv(row["manual_tags"])
        bucket = str(row["bucket"] or "")
        channel = str(row["channel_username"] or "")
        if not _should_export(
            surfaces=surfaces,
            bucket=bucket,
            manual_tags=manual_tags,
            channel=channel,
            include_channels=normalized_channels,
        ):
            continue
        seeds.append(_seed_from_row(row, surfaces=surfaces, manual_tags=manual_tags))
        if len(seeds) >= limit:
            break
    market_seed = market_context_lens_seed(market_lens.current_context)
    if market_seed is not None:
        market_seed.setdefault("contract_version", RADAR_INTELLIGENCE_CONTRACT_VERSION)
        market_seed.setdefault("intelligence_contract_version", INTELLIGENCE_CONTRACT_VERSION)
        seeds.append(market_seed)

    for seed in seeds:
        seed.update(period_fields)

    _atomic_write_json(target_path, seeds)
    market_pack_path = _market_pack_path_for(target_path, clean_week)
    _atomic_write_json(market_pack_path, market_pack)
    return OpportunitySeedExportResult(
        week_label=clean_week,
        output_path=str(target_path),
        seed_count=len(seeds),
        scanned_count=len(rows),
        knowledge_thread_count=len(knowledge_threads),
        knowledge_threads=[
            {
                "slug": thread.get("slug"),
                "title": thread.get("title"),
                "source_atom_ids": thread.get("source_atom_ids") or [],
            }
            for thread in knowledge_threads
        ],
        market_pack_path=str(market_pack_path),
        market_pain_pack=market_pack,
        market_lens_path=market_lens.current_path,
        market_baseline_path=market_lens.baseline_path,
        market_delta_path=market_lens.delta_path,
        market_context_lens=market_lens.current_context,
        run_date=period_fields["run_date"],
        generated_at=period_fields["generated_at"],
        reporting_week=period_fields["reporting_week"],
        period_mode=period_fields["period_mode"],
        analysis_period_start=period_fields["analysis_period_start"],
        analysis_period_end=period_fields["analysis_period_end"],
    )


def classify_demand_surfaces(text: str) -> list[str]:
    lowered = text.lower()
    surfaces: list[str] = []
    for surface, patterns in SURFACE_PATTERNS:
        if surface == "creator_content_gap":
            has_context = any(pattern in lowered for pattern in CREATOR_CONTEXT_TERMS)
            has_discovery_gap = any(pattern in lowered for pattern in CREATOR_DISCOVERY_TERMS)
            if has_context and has_discovery_gap:
                surfaces.append(surface)
            continue
        if any(pattern in lowered for pattern in patterns):
            surfaces.append(surface)
    return surfaces


def _fetch_recent_posts(
    connection: sqlite3.Connection,
    analysis_period_start: str,
    analysis_period_end: str,
    *,
    scan_limit: int,
) -> list[sqlite3.Row]:
    register_reporting_period_sqlite(connection)
    return list(
        connection.execute(
            """
            SELECT
                p.id AS post_id,
                p.raw_post_id,
                p.channel_username,
                p.posted_at,
                p.content,
                p.bucket,
                p.signal_score,
                p.user_adjusted_score,
                p.score_breakdown,
                r.message_id,
                r.message_url,
                r.view_count,
                (
                    SELECT GROUP_CONCAT(tag)
                    FROM user_post_tags
                    WHERE post_id = p.id
                ) AS manual_tags,
                (
                    SELECT GROUP_CONCAT(projects.name)
                    FROM post_project_links
                    INNER JOIN projects ON projects.id = post_project_links.project_id
                    WHERE post_project_links.post_id = p.id
                ) AS project_names
            FROM posts p
            INNER JOIN raw_posts r ON r.id = p.raw_post_id
            WHERE reporting_utc_micros(p.posted_at) >= reporting_utc_micros(?)
              AND reporting_utc_micros(p.posted_at) < reporting_utc_micros(?)
            ORDER BY
                CASE p.bucket
                    WHEN 'strong' THEN 0
                    WHEN 'watch' THEN 1
                    WHEN 'cultural' THEN 2
                    ELSE 3
                END,
                COALESCE(p.user_adjusted_score, p.signal_score, 0) DESC,
                reporting_utc_micros(p.posted_at) DESC,
                p.id DESC
            LIMIT ?
            """,
            (analysis_period_start, analysis_period_end, scan_limit),
        ).fetchall()
    )


def _should_export(
    *,
    surfaces: list[str],
    bucket: str,
    manual_tags: list[str],
    channel: str,
    include_channels: set[str],
) -> bool:
    if surfaces:
        return True
    if bucket in ACTIONABLE_BUCKETS:
        return True
    if ACTIONABLE_TAGS.intersection(manual_tags):
        return True
    return _normalize_channel(channel) in include_channels


def _seed_from_row(
    row: sqlite3.Row,
    *,
    surfaces: list[str],
    manual_tags: list[str],
) -> dict[str, object]:
    content = " ".join(str(row["content"] or "").split())
    channel = str(row["channel_username"] or "")
    message_id = int(row["message_id"] or 0)
    source_url = str(row["message_url"] or "").strip() or _message_url(channel, message_id)
    mvp_shape = infer_mvp_shape(content, surfaces)
    bucket = str(row["bucket"] or "")
    return {
        "upstream_id": f"telegram:{channel}:{message_id or row['post_id']}",
        "contract_version": RADAR_INTELLIGENCE_CONTRACT_VERSION,
        "intelligence_contract_version": INTELLIGENCE_CONTRACT_VERSION,
        "captured_at": str(row["posted_at"]),
        "title": mvp_shape,
        "text": content,
        "snippet": _truncate(content, 260),
        "source_url": source_url,
        "channel_username": channel,
        "post_id": str(row["post_id"]),
        "bucket": bucket,
        "signal_score": _optional_float(row["signal_score"]),
        "user_adjusted_score": _optional_float(row["user_adjusted_score"]),
        "manual_tags": manual_tags,
        "project_names": _split_csv(row["project_names"]),
        "demand_surfaces": surfaces,
        "demand_signal_type": surfaces[0] if surfaces else "scored_telegram_signal",
        "evidence_strength": bucket or ("manual" if manual_tags else "unscored"),
        "pain_statement": infer_pain_statement(content),
        "mvp_shape": mvp_shape,
        "target_user": infer_target_user(content),
        "verification_needed": infer_verification_needed(surfaces),
        "anti_complexity_note": infer_anti_complexity_note(mvp_shape),
        "private": False,
    }


def _seed_from_knowledge_thread(thread: dict) -> dict[str, object]:
    atoms = thread.get("atoms") or []
    first_atom = atoms[0] if atoms else {}
    claim = str(first_atom.get("claim") or (thread.get("current_claims") or [""])[0])
    summary = str(first_atom.get("summary") or thread.get("summary") or claim)
    atom_types = list(thread.get("atom_types") or [])
    surfaces = _demand_surfaces_from_atom_types(atom_types)
    source_urls = list(thread.get("source_urls") or [])
    source_url = source_urls[0] if source_urls else ""
    text = " ".join(part for part in (thread.get("title"), summary, claim) if part)
    mvp_shape = infer_mvp_shape(text, surfaces)
    return {
        "upstream_id": f"knowledge-thread:{thread.get('slug')}",
        "contract_version": RADAR_INTELLIGENCE_CONTRACT_VERSION,
        "intelligence_contract_version": INTELLIGENCE_CONTRACT_VERSION,
        "captured_at": str(thread.get("last_seen_at") or ""),
        "title": mvp_shape,
        "text": text,
        "snippet": _truncate(text, 260),
        "source_url": source_url,
        "source_urls": source_urls,
        "channel_username": ",".join(thread.get("source_channels") or []),
        "post_id": "",
        "bucket": "knowledge_thread",
        "signal_score": None,
        "user_adjusted_score": None,
        "manual_tags": [],
        "project_names": [],
        "demand_surfaces": surfaces,
        "demand_signal_type": surfaces[0] if surfaces else "knowledge_thread",
        "evidence_strength": "knowledge_thread",
        "pain_statement": infer_pain_statement(claim or summary),
        "mvp_shape": mvp_shape,
        "target_user": infer_target_user(text),
        "verification_needed": infer_verification_needed(surfaces),
        "anti_complexity_note": infer_anti_complexity_note(mvp_shape),
        "private": False,
        "source_kind": "knowledge_thread",
        "knowledge_thread_slug": thread.get("slug"),
        "knowledge_thread_title": thread.get("title"),
        "knowledge_thread_status": thread.get("status"),
        "knowledge_atom_types": atom_types,
        "source_atom_ids": thread.get("source_atom_ids") or [],
    }


def _demand_surfaces_from_atom_types(atom_types: list[str]) -> list[str]:
    surfaces = []
    if "market_signal" in atom_types:
        surfaces.append("market_signal")
    if "workflow_pattern" in atom_types:
        surfaces.extend(["manual_workaround", "workflow_automation"])
    if "case_study" in atom_types:
        surfaces.append("competitor_traction")
    if "opinion_shift" in atom_types:
        surfaces.append("repeated_questions")
    unique = []
    for surface in surfaces:
        if surface not in unique:
            unique.append(surface)
    return unique or ["knowledge_thread"]


def infer_mvp_shape(text: str, surfaces: list[str]) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("транскрибац", "transcrib", "transcript")) and any(
        term in lowered for term in ("видео", "video", "youtube")
    ):
        return "Video Transcription SEO Microtool"
    if "google" in lowered and any(term in lowered for term in ("сайт", "website", "site")) and any(
        term in lowered for term in ("трафик", "traffic", "переход", "seo", "поиск")
    ):
        return "SEO Micro-Site Growth Analyzer"
    if any(
        term in lowered
        for term in ("app store", "stores", "store listing", " в сторах", " стора", " сторы", "магазин приложений")
    ) and any(
        term in lowered for term in ("трафик", "traffic", "поиск", "search", "google")
    ):
        return "Store-Search Micro-App Opportunity Scout"
    if _has_telegram_channel_search_gap(lowered):
        return "Telegram Channel SEO Site Generator"
    if "youtube" in lowered and any(term in lowered for term in ("podcast", "listen", "audio")):
        return "YouTube-to-Podcast Feed Experiment"
    if any(term in lowered for term in ("dictation", "voice", "whisper", "диктов")):
        return "Hotkey Dictation Workflow Probe"
    if any(term in lowered for term in ("lead", "sla", "response")):
        return "Lead Response SLA Monitor"
    if any(term in lowered for term in ("training", "rollout", "adoption", "обуч")):
        return "AI Rollout Training OS"
    if any(term in lowered for term in ("workflow", "n8n", "agent", "approval", "процесс")):
        return "Workflow-to-Agent Studio"
    if any(term in lowered for term in ("pdf", "ocr", "document", "документ")):
        return "Document-to-Structured-Data Validator"
    if "creator_content_gap" in surfaces:
        return "Creator Content Discovery Gap Report"
    if "manual_workaround" in surfaces:
        return "Manual Workflow Automation Probe"
    return f"Opportunity Probe: {_truncate(text, 72)}"


def _has_telegram_channel_search_gap(lowered: str) -> bool:
    if not any(term in lowered for term in ("telegram", "телеграм")):
        return False
    channel_terms = ("канал", "channel", "контент", "content", "пост", "posts")
    strong_discovery_terms = ("seo", "индекс", "archive", "архив")
    if any(term in lowered for term in strong_discovery_terms) and any(
        term in lowered for term in channel_terms
    ):
        return True
    return any(
        _terms_near(lowered, discovery_term, channel_term, max_distance=120)
        for discovery_term in ("поиск", "search")
        for channel_term in channel_terms
    )


def _terms_near(text: str, first: str, second: str, *, max_distance: int) -> bool:
    first_index = text.find(first)
    while first_index >= 0:
        second_index = text.find(second, max(0, first_index - max_distance), first_index + max_distance)
        if second_index >= 0:
            return True
        first_index = text.find(first, first_index + len(first))
    return False


def infer_pain_statement(text: str) -> str:
    sentence = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
    return _truncate(sentence or text, 220)


def infer_target_user(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("channel", "канал", "creator", "контент")):
        return "Telegram creators and channel operators"
    if any(term in lowered for term in ("support", "sla", "lead", "sales")):
        return "Small teams handling inbound leads or support queues"
    if any(term in lowered for term in ("developer", "github", "api", "sdk")):
        return "Builders and technical operators"
    if any(term in lowered for term in ("training", "rollout", "adoption", "команда")):
        return "Teams rolling out AI workflows"
    return "Solo operators with repeatable workflow pain"


def infer_verification_needed(surfaces: list[str]) -> list[str]:
    gaps = ["willingness-to-pay signal"]
    if "competitor_traction" in surfaces:
        gaps.append("competitor pricing and positioning comparison")
    if "search_intent" in surfaces:
        gaps.append("repeatable search query examples")
    if "manual_workaround" in surfaces:
        gaps.append("screenshots or concrete examples of the manual workaround")
    if "creator_content_gap" in surfaces:
        gaps.append("creator interview or public channel owner feedback")
    return gaps


def infer_anti_complexity_note(mvp_shape: str) -> str:
    if mvp_shape == "Telegram Channel SEO Site Generator":
        return "Only public channel URL -> static preview + SEO/searchability report."
    if mvp_shape == "AI Rollout Training OS":
        return "One team, one workflow, one training runbook. No LMS."
    if mvp_shape == "Workflow-to-Agent Studio":
        return "One imported workflow -> one agent spec. No general visual builder."
    return "Ship one proof artifact. Do not build a platform before demand is verified."


def _message_url(channel: str, message_id: int) -> str:
    username = channel.strip().lstrip("@")
    if not username or message_id <= 0:
        return ""
    return f"https://t.me/{username}/{message_id}"


def _split_csv(value: object) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_channel(channel: str) -> str:
    return channel.strip().lower().lstrip("@")


def _truncate(text: str, limit: int) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _market_pack_path_for(seed_path: Path, week_label: str) -> Path:
    if seed_path.parent == OUTPUT_DIR:
        return MARKET_PACK_DIR / f"{week_label}.json"
    return seed_path.with_name(f"{seed_path.stem}.market_pain_pack.json")


def _market_lens_output_root_for(seed_path: Path) -> Path | None:
    if seed_path.parent == OUTPUT_DIR:
        return None
    return seed_path.with_name(f"{seed_path.stem}.market_context_lens")


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
