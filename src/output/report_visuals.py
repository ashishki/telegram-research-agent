"""Deterministic, offline Report V2 visualization components.

The module is intentionally independent from both reader surfaces.  Weekly
Brief V2 and Knowledge Atlas V2 can consume the same validated component HTML
without duplicating rendering semantics.  It never reads the filesystem,
environment, clock, or network and it does not infer evidence or decisions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from html import escape
import math
import re
from typing import Callable
from urllib.parse import urlsplit


REPORT_VISUALS_CONTRACT_VERSION = "report_visuals.v1"

_SCHEMA_PREFIX = "report_visual."
_COMPONENT_SCHEMAS = {
    "decision_matrix": f"{_SCHEMA_PREFIX}decision_matrix.v1",
    "reaction_funnel": f"{_SCHEMA_PREFIX}reaction_funnel.v1",
    "radar_gate": f"{_SCHEMA_PREFIX}radar_gate.v1",
    "project_impact": f"{_SCHEMA_PREFIX}project_impact.v1",
    "knowledge_graph": f"{_SCHEMA_PREFIX}knowledge_graph.v1",
    "thread_timeline": f"{_SCHEMA_PREFIX}thread_timeline.v1",
    "source_thread_heatmap": f"{_SCHEMA_PREFIX}source_thread_heatmap.v1",
    "evidence_maturity": f"{_SCHEMA_PREFIX}evidence_maturity.v1",
    "learning_progression": f"{_SCHEMA_PREFIX}learning_progression.v1",
    "evidence_badge": f"{_SCHEMA_PREFIX}evidence_badge.v1",
}
SUPPORTED_VISUAL_SCHEMAS = tuple(_COMPONENT_SCHEMAS.values())
_SCHEMA_TO_COMPONENT = {schema: name for name, schema in _COMPONENT_SCHEMAS.items()}

_DATA_STATUSES = {"available", "empty", "unavailable", "stale"}
_RENDER_STATUSES = {"complete", "partial", "failed"}
_CONFIDENCE = {"low", "medium", "high"}
_MATURITY = {
    "single_source",
    "repeated_signal",
    "multi_channel",
    "primary_verified",
    "externally_corroborated",
    "decision_grade",
}
_COMMON_REQUIRED = {
    "schema_version",
    "component_id",
    "title_ru",
    "summary_ru",
    "run_id",
    "reporting_week",
    "analysis_period_start",
    "analysis_period_end",
    "data_status",
    "source_refs",
    "data_note_ru",
}
_COMMON_OPTIONAL = {
    "partial_reasons_ru",
    "state_reason_ru",
    "stale_from_run_id",
    "stale_from_period",
}
_COMPONENT_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_WEEK_RE = re.compile(r"^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$")
_SAFE_OPAQUE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#@+\-=]{0,299}$")
_SAFE_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._+@ -]+$")
_OPAQUE_REF_SCHEMES = {
    "artifact",
    "atom",
    "evidence",
    "feedback",
    "manifest",
    "radar",
    "reaction",
    "signal",
    "source",
    "thread",
}
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


class ReportVisualValidationError(ValueError):
    """Raised by the strict validator before safe render fallback handling."""


@dataclass(frozen=True, slots=True)
class ReportVisualResult:
    """Stable output contract shared by every Report V2 visual component."""

    html: str
    component_id: str
    component_type: str
    schema_version: str
    render_status: str
    data_status: str
    source_ref_count: int
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.render_status not in _RENDER_STATUSES:
            raise ValueError(f"invalid render_status: {self.render_status}")
        if self.data_status not in _DATA_STATUSES:
            raise ValueError(f"invalid data_status: {self.data_status}")

    def as_dict(self) -> dict[str, object]:
        """Return the exact serializable rendering receipt."""

        return asdict(self)


REPORT_VISUALS_CSS = """
.irx-report{box-sizing:border-box;max-width:1440px;margin:0 auto;padding:24px;color:#17212b;background:#fff;font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.irx-report *{box-sizing:border-box}
.irx-report__title{margin:0 0 24px;font-size:2rem}
.irx-visual{margin:0 0 24px;padding:20px;border:1px solid #c8d0d8;border-radius:12px;background:#fff;overflow-wrap:anywhere}
.irx-visual:focus-within{outline:3px solid #1d4ed8;outline-offset:2px}
.irx-visual__heading{margin:0 0 4px;font-size:1.35rem}
.irx-visual__summary{margin:0 0 12px;color:#334155}
.irx-visual__meta,.irx-visual__note{margin:12px 0 0;color:#475569;font-size:.92rem}
.irx-visual__state{margin:12px 0;padding:12px;border-left:5px solid #65717d;background:#f1f5f9}
.irx-visual__state--partial,.irx-visual__state--stale{border-color:#92400e;background:#fffbeb}
.irx-visual__state--failed{border-color:#be123c;background:#fff1f2}
.irx-visual__grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:12px;margin-top:14px}
.irx-visual__region,.irx-visual__card{min-width:0;padding:12px;border:1px solid #cbd5e1;border-radius:8px;background:#f8fafc}
.irx-visual__region h3,.irx-visual__card h3{margin:0 0 8px;font-size:1rem}
.irx-visual__list{margin:0;padding-left:22px}
.irx-visual__list li+li{margin-top:8px}
.irx-visual__item--primary{border-left:4px solid #166534;padding-left:8px}
.irx-visual__item--defer{border-left:4px dashed #65717d;padding-left:8px}
.irx-visual__status{display:inline-block;padding:2px 8px;border:1px solid currentColor;border-radius:999px;font-weight:700}
.irx-visual__status--act,.irx-visual__status--pass,.irx-visual__status--confirmed{color:#166534}
.irx-visual__status--study,.irx-visual__status--watch{color:#1d4ed8}
.irx-visual__status--blocked,.irx-visual__status--missing{color:#be123c}
.irx-visual__status--neutral{color:#475569}
.irx-visual__flow{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,150px),1fr));gap:12px;list-style:none;padding:0;margin:14px 0}
.irx-visual__flow li{position:relative;padding:14px;border:2px solid #1d4ed8;border-radius:8px;background:#eff6ff}
.irx-visual__flow strong{display:block;font-size:1.35rem}
.irx-visual__split{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.irx-visual__table-wrap,.irx-visual__canvas{max-width:100%;overflow-x:auto;overscroll-behavior-inline:contain}
.irx-visual table{width:100%;border-collapse:collapse;margin-top:12px}
.irx-visual th,.irx-visual td{padding:9px;border:1px solid #cbd5e1;text-align:left;vertical-align:top}
.irx-visual th{background:#f1f5f9}
.irx-visual__heatmap th:first-child{position:sticky;left:0;z-index:2;background:#f1f5f9}
.irx-visual__heatmap thead th:first-child{z-index:3}
.irx-visual tr[data-actionable="true"]{border-left:5px solid #166534}
.irx-visual tr[data-actionable="false"]{border-left:5px dashed #65717d}
.irx-visual__mobile-label{display:none;font-weight:700}
.irx-visual svg{display:block;max-width:100%;height:auto;margin:12px 0;background:#f8fafc;border:1px solid #cbd5e1}
.irx-visual__graph-svg{min-width:920px}
.irx-visual svg text{fill:#17212b;font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
.irx-visual__relations{margin-top:12px}
.irx-visual__spark{margin:14px 0;padding:12px;border:1px solid #cbd5e1;border-radius:8px}
.irx-visual__bar-row{display:grid;grid-template-columns:minmax(180px,1fr) minmax(120px,3fr) auto;gap:10px;align-items:center;margin:9px 0}
.irx-visual__bar-track{height:18px;border:1px solid #94a3b8;background:#f8fafc}
.irx-visual__bar{height:100%;background:#1d4ed8}
.irx-visual__heat-0{background:#fff}
.irx-visual__heat-1{background:#dbeafe}
.irx-visual__heat-2{background:#bfdbfe}
.irx-visual__heat-3{background:#93c5fd}
.irx-visual__heat-4{background:#60a5fa}
.irx-visual__unknown{background:#f1f5f9;color:#475569;border:2px dashed #65717d}
.irx-visual__badge-pair{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}
.irx-visual__badge{min-width:190px;padding:10px;border:2px solid #1d4ed8;border-radius:8px;background:#eff6ff}
.irx-visual__badge--maturity{border-style:dashed;border-color:#92400e;background:#fffbeb}
.irx-visual a{color:#1d4ed8;text-decoration-thickness:2px;text-underline-offset:2px}
.irx-visual a:focus-visible{outline:3px solid #1d4ed8;outline-offset:2px}
@media (max-width:600px){.irx-report{padding:12px}.irx-visual{padding:14px}.irx-visual__grid,.irx-visual__split,.irx-visual__flow{grid-template-columns:1fr}.irx-visual__bar-row{grid-template-columns:1fr}.irx-visual__project thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}.irx-visual__project tr,.irx-visual__project td{display:block;width:100%}.irx-visual__project tr{margin:0 0 12px;border:1px solid #cbd5e1}.irx-visual__project td{border:0;border-bottom:1px solid #e2e8f0}.irx-visual__mobile-label{display:block}}
@media print{.irx-report{max-width:none;padding:0}.irx-visual{break-inside:avoid;border-color:#64748b}.irx-visual__table-wrap,.irx-visual__canvas{overflow:visible}.irx-visual__graph-svg{min-width:0}.irx-visual__heatmap th:first-child{position:static}.irx-visual a{color:#17212b;text-decoration:none}}
@media (prefers-reduced-motion:reduce){.irx-report *{scroll-behavior:auto!important}}
""".strip()


def report_visual_styles() -> str:
    """Return the fixed, scoped, offline CSS bundle."""

    return REPORT_VISUALS_CSS


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _fail(path: str, message: str) -> None:
    raise ReportVisualValidationError(f"{path}: {message}")


def _expect_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _fail(path, "ожидался объект")
    return value


def _expect_exact_fields(
    value: Mapping[str, object],
    *,
    required: set[str],
    optional: set[str] | None = None,
    path: str,
) -> None:
    if any(not isinstance(key, str) for key in value):
        _fail(path, "имена полей должны быть строками")
    allowed = required | (optional or set())
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        _fail(path, f"отсутствуют поля: {', '.join(missing)}")
    if unknown:
        _fail(path, f"неизвестные поля: {', '.join(unknown)}")


def _expect_str(
    value: object,
    path: str,
    *,
    russian: bool = False,
    max_length: int = 600,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        _fail(path, "ожидалась строка")
    if value != value.strip():
        _fail(path, "пробелы по краям запрещены")
    if not allow_empty and not value:
        _fail(path, "строка не может быть пустой")
    if len(value) > max_length:
        _fail(path, f"строка длиннее {max_length} символов")
    if any(ord(char) < 32 and char not in "\t\n" for char in value):
        _fail(path, "управляющие символы запрещены")
    if russian and value and not _CYRILLIC_RE.search(value):
        _fail(path, "reader-facing текст должен содержать русский язык")
    return value


def _expect_enum(value: object, choices: set[str], path: str) -> str:
    if not isinstance(value, str) or value not in choices:
        _fail(path, f"ожидалось одно из: {', '.join(sorted(choices))}")
    return value


def _expect_int(
    value: object,
    path: str,
    *,
    minimum: int = 0,
    maximum: int = 1_000_000_000,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(path, "ожидалось целое число")
    if value < minimum:
        _fail(path, f"значение должно быть не меньше {minimum}")
    if value > maximum:
        _fail(path, f"значение должно быть не больше {maximum}")
    return value


def _expect_number(
    value: object,
    path: str,
    *,
    minimum: float = 0.0,
    maximum: float = 1_000_000_000.0,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, "ожидалось число")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ReportVisualValidationError(
            f"{path}: число вне допустимого диапазона"
        ) from exc
    if not math.isfinite(number):
        _fail(path, "число должно быть конечным")
    if number < minimum:
        _fail(path, f"значение должно быть не меньше {minimum}")
    if number > maximum:
        _fail(path, f"значение должно быть не больше {_fmt_number_limit(maximum)}")
    return number


def _fmt_number_limit(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def _expect_list(value: object, path: str, *, maximum: int = 200) -> list[object]:
    if not isinstance(value, list):
        _fail(path, "ожидался список")
    if len(value) > maximum:
        _fail(path, f"список длиннее {maximum} элементов")
    return value


def _expect_string_list(
    value: object,
    path: str,
    *,
    russian: bool = False,
    maximum: int = 50,
    allow_empty: bool = True,
) -> list[str]:
    values = _expect_list(value, path, maximum=maximum)
    strings = [
        _expect_str(item, f"{path}[{index}]", russian=russian)
        for index, item in enumerate(values)
    ]
    if not allow_empty and not strings:
        _fail(path, "список не может быть пустым")
    if len(strings) != len(set(strings)):
        _fail(path, "повторяющиеся значения запрещены")
    return strings


def _expect_utc(value: object, path: str) -> datetime:
    text = _expect_str(value, path, max_length=30)
    if not text.endswith("Z"):
        _fail(path, "ожидалась UTC-дата с суффиксом Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ReportVisualValidationError(f"{path}: некорректная ISO-дата") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        _fail(path, "ожидалась UTC-дата")
    return parsed


def _validate_reference(value: object, path: str) -> str:
    text = _expect_str(value, path, max_length=300)
    if any(char.isspace() or ord(char) < 32 for char in text):
        _fail(path, "пробелы и управляющие символы в reference запрещены")
    if "\\" in text or ".." in text.split("/") or text.startswith(("/", "//")):
        _fail(path, "небезопасный абсолютный или родительский путь")
    try:
        split = urlsplit(text)
    except ValueError as exc:
        raise ReportVisualValidationError(f"{path}: некорректная URL-ссылка") from exc
    scheme = split.scheme.lower()
    if scheme in {"http", "https"}:
        try:
            split.port
        except ValueError as exc:
            raise ReportVisualValidationError(
                f"{path}: некорректный порт HTTP(S)-ссылки"
            ) from exc
        if (
            not split.hostname
            or split.username is not None
            or split.password is not None
        ):
            _fail(path, "HTTP(S)-ссылка требует host и запрещает credentials")
        return text
    if scheme in {"javascript", "data", "file", "vbscript"}:
        _fail(path, "опасная схема ссылки запрещена")
    if scheme and scheme not in _OPAQUE_REF_SCHEMES:
        _fail(
            path,
            "разрешены только HTTP(S), относительный путь или известный opaque ref",
        )
    if scheme in _OPAQUE_REF_SCHEMES and (split.netloc or "://" in text):
        _fail(path, "opaque ref не может быть URL-shaped ссылкой")
    if not _SAFE_OPAQUE_REF_RE.fullmatch(text):
        _fail(path, "небезопасный reference/path")
    return text


def _validate_local_path(value: object, path: str) -> str:
    text = _expect_str(value, path, max_length=240)
    if "://" in text or text.startswith(("/", "~", "//")) or "\\" in text:
        _fail(path, "разрешен только относительный POSIX-путь")
    parts = text.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        _fail(path, "пустые, текущие и родительские сегменты пути запрещены")
    if any(any(ord(char) < 32 for char in part) for part in parts):
        _fail(path, "управляющие символы запрещены")
    if any(not _SAFE_PATH_SEGMENT_RE.fullmatch(part) for part in parts):
        _fail(path, "путь содержит недопустимые символы")
    return text


def _validate_common(spec: Mapping[str, object], component_fields: set[str]) -> None:
    _expect_exact_fields(
        spec,
        required=_COMMON_REQUIRED | component_fields,
        optional=_COMMON_OPTIONAL,
        path="spec",
    )
    schema = _expect_str(spec["schema_version"], "schema_version", max_length=80)
    if schema not in SUPPORTED_VISUAL_SCHEMAS:
        _fail("schema_version", "неподдерживаемая версия schema")
    component_id = _expect_str(spec["component_id"], "component_id", max_length=64)
    if not _COMPONENT_ID_RE.fullmatch(component_id):
        _fail("component_id", "ожидался безопасный kebab-case id")
    _expect_str(spec["title_ru"], "title_ru", russian=True, max_length=160)
    _expect_str(spec["summary_ru"], "summary_ru", russian=True, max_length=500)
    _expect_str(spec["run_id"], "run_id", max_length=160)
    reporting_week = _expect_str(spec["reporting_week"], "reporting_week", max_length=8)
    if not _WEEK_RE.fullmatch(reporting_week):
        _fail("reporting_week", "ожидался ISO week вида YYYY-Www")
    start = _expect_utc(spec["analysis_period_start"], "analysis_period_start")
    end = _expect_utc(spec["analysis_period_end"], "analysis_period_end")
    if start >= end:
        _fail("analysis_period", "начало должно предшествовать окончанию")
    year_text, week_text = reporting_week.split("-W", 1)
    try:
        expected_start = datetime.fromisocalendar(
            int(year_text), int(week_text), 1
        ).replace(tzinfo=start.tzinfo)
    except ValueError as exc:
        raise ReportVisualValidationError(
            "reporting_week: недопустимая ISO-неделя для указанного года"
        ) from exc
    if start != expected_start or end != expected_start + timedelta(weeks=1):
        _fail(
            "analysis_period",
            "границы должны точно совпадать с завершенной ISO-неделей reporting_week",
        )
    data_status = _expect_enum(spec["data_status"], _DATA_STATUSES, "data_status")
    refs = _expect_list(spec["source_refs"], "source_refs", maximum=100)
    validated_refs = [
        _validate_reference(ref, f"source_refs[{index}]")
        for index, ref in enumerate(refs)
    ]
    if len(validated_refs) != len(set(validated_refs)):
        _fail("source_refs", "повторяющиеся ссылки запрещены")
    _expect_str(spec["data_note_ru"], "data_note_ru", russian=True, max_length=800)

    reasons = _expect_string_list(
        spec.get("partial_reasons_ru", []),
        "partial_reasons_ru",
        russian=True,
        maximum=20,
    )
    state_reason = spec.get("state_reason_ru")
    if state_reason is not None:
        _expect_str(state_reason, "state_reason_ru", russian=True, max_length=500)
    if data_status in {"unavailable", "stale"} and state_reason is None:
        _fail("state_reason_ru", f"обязателен для data_status={data_status}")
    if data_status in {"available", "empty", "stale"} and not validated_refs:
        _fail("source_refs", f"{data_status}-компонент требует хотя бы один source ref")
    if data_status == "unavailable" and validated_refs:
        _fail(
            "source_refs",
            "unavailable-компонент не должен ссылаться на недоступные данные",
        )
    if data_status == "empty" and reasons:
        _fail("partial_reasons_ru", "честный empty не может одновременно быть partial")
    if data_status in {"available", "empty"} and state_reason is not None:
        _fail("state_reason_ru", f"не разрешен для data_status={data_status}")

    stale_run = spec.get("stale_from_run_id")
    stale_period = spec.get("stale_from_period")
    if data_status == "stale":
        stale_run_text = _expect_str(stale_run, "stale_from_run_id", max_length=160)
        stale_text = _expect_str(stale_period, "stale_from_period", max_length=8)
        if not _WEEK_RE.fullmatch(stale_text):
            _fail("stale_from_period", "ожидался ISO week вида YYYY-Www")
        stale_year, stale_week = stale_text.split("-W", 1)
        try:
            stale_start = datetime.fromisocalendar(
                int(stale_year), int(stale_week), 1
            ).replace(tzinfo=start.tzinfo)
        except ValueError as exc:
            raise ReportVisualValidationError(
                "stale_from_period: недопустимая ISO-неделя для указанного года"
            ) from exc
        if stale_run_text == spec["run_id"]:
            _fail(
                "stale_from_run_id",
                "устаревший источник должен относиться к другому run",
            )
        if stale_start >= expected_start:
            _fail(
                "stale_from_period",
                "устаревший источник должен относиться к предыдущему reporting week",
            )
    elif stale_run is not None or stale_period is not None:
        _fail("spec", "stale_from_* разрешены только при data_status=stale")


def _require_collection_state(
    spec: Mapping[str, object],
    collection: Sequence[object],
    path: str,
    *,
    available_must_have_data: bool = True,
) -> None:
    status = str(spec["data_status"])
    if status in {"empty", "unavailable"} and collection:
        _fail(path, f"{status}-состояние требует пустую коллекцию")
    if status in {"available", "stale"} and available_must_have_data and not collection:
        _fail(path, f"{status}-состояние требует данные")


def _render_status(spec: Mapping[str, object], *, extra_partial: bool = False) -> str:
    if spec["data_status"] in {"unavailable", "stale"}:
        return "partial"
    if spec.get("partial_reasons_ru") or extra_partial:
        return "partial"
    return "complete"


def _result_warnings(
    spec: Mapping[str, object], *extra: str, extra_partial: bool = False
) -> tuple[str, ...]:
    warnings = sorted(spec.get("partial_reasons_ru", []))
    if spec["data_status"] in {"unavailable", "stale"}:
        warnings.append(str(spec["state_reason_ru"]))
    if extra_partial:
        warnings.extend(extra)
    return tuple(warnings)


def _state_banner(spec: Mapping[str, object]) -> str:
    status = str(spec["data_status"])
    reasons = sorted(spec.get("partial_reasons_ru", []))
    parts: list[str] = []
    if status in {"unavailable", "stale"}:
        label = "Данные недоступны" if status == "unavailable" else "Данные устарели"
        stale_note = ""
        if status == "stale":
            stale_note = (
                f" Исходный период: {_e(spec['stale_from_period'])}; "
                "эти данные не участвуют в решении текущего запуска."
            )
        parts.append(
            f'<div class="irx-visual__state irx-visual__state--{status}" role="status">'
            f"<strong>{label}.</strong> {_e(spec['state_reason_ru'])}{stale_note}</div>"
        )
    if reasons:
        items = "".join(f"<li>{_e(reason)}</li>" for reason in reasons)
        parts.append(
            '<div class="irx-visual__state irx-visual__state--partial" role="status">'
            f"<strong>Данные рассчитаны частично.</strong><ul>{items}</ul></div>"
        )
    return "".join(parts)


def _state_message(component_type: str, data_status: str) -> str:
    empty = {
        "decision_matrix": "Решений по данным завершенного периода нет.",
        "reaction_funnel": (
            "За период личные реакции не обнаружены. Это не означает отрицательный интерес."
        ),
        "radar_gate": "Успешный запуск MVP Radar не выбрал кандидата.",
        "project_impact": "Подтвержденного влияния на активные проекты нет.",
        "knowledge_graph": (
            "Ни одна каноническая тема не прошла текущий порог отображения."
        ),
        "thread_timeline": (
            "Исторических снимков пока недостаточно для временного ряда."
        ),
        "source_thread_heatmap": (
            "За период классифицированные источники не внесли вклад в выбранные темы."
        ),
        "evidence_maturity": "Квалифицирующих канонических тем за период нет.",
        "learning_progression": "Прогресс обучения еще не подтвержден.",
        "evidence_badge": "Оценка уверенности и зрелости доказательств отсутствует.",
    }
    if data_status == "empty":
        return empty[component_type]
    return "Текущие значения не показаны: исходные данные недоступны."


def _section(
    spec: Mapping[str, object],
    component_type: str,
    body: str,
    *,
    render_status: str,
    source_ref_count: int,
) -> str:
    component_id = str(spec["component_id"])
    heading_id = f"{component_id}-title"
    visual_role = "supporting" if component_type == "evidence_badge" else "data"
    return (
        f'<section class="irx-visual irx-visual--{_e(component_type)}" '
        f'data-irx-visual="true" data-component="{_e(component_type)}" '
        f'data-component-id="{_e(component_id)}" '
        f'data-schema-version="{_e(spec["schema_version"])}" '
        f'data-render-status="{_e(render_status)}" '
        f'data-data-status="{_e(spec["data_status"])}" '
        f'data-source-ref-count="{source_ref_count}" '
        f'data-visual-role="{visual_role}" aria-labelledby="{_e(heading_id)}">'
        f'<h2 class="irx-visual__heading" id="{_e(heading_id)}">{_e(spec["title_ru"])}</h2>'
        f'<p class="irx-visual__summary">{_e(spec["summary_ru"])}</p>'
        f'<p class="irx-visual__meta">Период: {_e(spec["reporting_week"])}; '
        f"ссылок происхождения данных: {source_ref_count}.</p>"
        f"{_state_banner(spec)}{body}"
        f'<p class="irx-visual__note"><strong>Данные и ограничение:</strong> '
        f"{_e(spec['data_note_ru'])}</p>"
        "</section>"
    )


_DECISION_ORDER = ("act", "study", "watch", "ignore")
_DECISION_LABELS = {
    "act": "Действовать",
    "study": "Изучить",
    "watch": "Наблюдать",
    "ignore": "Отложить",
}
_CONFIDENCE_LABELS = {"low": "низкая", "medium": "средняя", "high": "высокая"}
_MATURITY_LABELS = {
    "single_source": "один источник",
    "repeated_signal": "повторяющийся сигнал",
    "multi_channel": "несколько каналов",
    "primary_verified": "проверено первичным источником",
    "externally_corroborated": "подтверждено внешне",
    "decision_grade": "достаточно для решения",
}


def _validate_decision_matrix(spec: Mapping[str, object]) -> None:
    _validate_common(spec, {"items"})
    items = _expect_list(spec["items"], "items", maximum=12)
    _require_collection_state(spec, items, "items")
    seen_refs: set[str] = set()
    counts = {decision: 0 for decision in _DECISION_ORDER}
    primary_count = 0
    defer_count = 0
    for index, raw_item in enumerate(items):
        path = f"items[{index}]"
        item = _expect_mapping(raw_item, path)
        _expect_exact_fields(
            item,
            required={
                "decision",
                "label_ru",
                "signal_ref",
                "confidence",
                "evidence_maturity",
                "emphasis",
            },
            path=path,
        )
        decision = _expect_enum(
            item["decision"], set(_DECISION_ORDER), f"{path}.decision"
        )
        _expect_str(item["label_ru"], f"{path}.label_ru", russian=True, max_length=240)
        signal_ref = _validate_reference(item["signal_ref"], f"{path}.signal_ref")
        if signal_ref in seen_refs:
            _fail(f"{path}.signal_ref", "signal_ref должен быть уникальным")
        seen_refs.add(signal_ref)
        _expect_enum(item["confidence"], _CONFIDENCE, f"{path}.confidence")
        _expect_enum(item["evidence_maturity"], _MATURITY, f"{path}.evidence_maturity")
        emphasis = _expect_enum(
            item["emphasis"],
            {"none", "primary_action", "explicit_defer"},
            f"{path}.emphasis",
        )
        if emphasis == "primary_action":
            if decision != "act":
                _fail(f"{path}.emphasis", "primary_action допустим только в act")
            primary_count += 1
        if emphasis == "explicit_defer":
            if decision != "ignore":
                _fail(f"{path}.emphasis", "explicit_defer допустим только в ignore")
            defer_count += 1
        counts[decision] += 1
        if counts[decision] > 3:
            _fail("items", f"в категории {decision} разрешено не больше трех решений")
    if spec["data_status"] in {"available", "stale"}:
        if primary_count != 1:
            _fail("items", "нужно ровно одно явно отмеченное primary_action")
        if defer_count != 1:
            _fail("items", "нужно ровно одно явно отмеченное explicit_defer")


def _render_decision_matrix(
    spec: Mapping[str, object],
) -> tuple[str, bool, tuple[str, ...]]:
    items = list(spec["items"])
    if spec["data_status"] == "unavailable":
        return (
            f"<p>{_e(_state_message('decision_matrix', 'unavailable'))}</p>",
            False,
            (),
        )
    if spec["data_status"] == "empty":
        buckets = {decision: [] for decision in _DECISION_ORDER}
    else:
        emphasis_rank = {"primary_action": 0, "explicit_defer": 0, "none": 1}
        ordered = sorted(
            items,
            key=lambda item: (
                _DECISION_ORDER.index(str(item["decision"])),
                emphasis_rank[str(item["emphasis"])],
                str(item["label_ru"]).casefold(),
                str(item["signal_ref"]),
            ),
        )
        buckets = {
            decision: [item for item in ordered if item["decision"] == decision]
            for decision in _DECISION_ORDER
        }
    regions: list[str] = []
    for decision in _DECISION_ORDER:
        rows: list[str] = []
        for item in buckets[decision]:
            emphasis = str(item["emphasis"])
            item_class = ""
            prefix = ""
            if emphasis == "primary_action":
                item_class = ' class="irx-visual__item--primary"'
                prefix = "Главное действие. "
            elif emphasis == "explicit_defer":
                item_class = ' class="irx-visual__item--defer"'
                prefix = "Явно отложить. "
            rows.append(
                f"<li{item_class}><strong>{_e(prefix + str(item['label_ru']))}</strong> "
                f"Уверенность: {_e(_CONFIDENCE_LABELS[str(item['confidence'])])}; "
                f"зрелость доказательств: "
                f"{_e(_MATURITY_LABELS[str(item['evidence_maturity'])])}.</li>"
            )
        if not rows:
            rows.append("<li>Решений для этой категории нет.</li>")
        regions.append(
            '<section class="irx-visual__region">'
            f"<h3>{_e(_DECISION_LABELS[decision])}</h3>"
            f'<ul class="irx-visual__list">{"".join(rows)}</ul></section>'
        )
    if spec["data_status"] == "empty":
        lead = f"<p>{_e(_state_message('decision_matrix', 'empty'))}</p>"
    else:
        lead = ""
    return lead + f'<div class="irx-visual__grid">{"".join(regions)}</div>', False, ()


_REACTION_STAGE_KEYS = (
    "detected",
    "posts_resolved",
    "atoms_linked",
    "threads_linked",
    "signals_selected",
)
_REACTION_STAGE_LABELS = {
    "detected": "Реакции",
    "posts_resolved": "Посты найдены",
    "atoms_linked": "Связаны с атомами",
    "threads_linked": "Связаны с темами",
    "signals_selected": "Повлияли на сигналы",
}


def _validate_reaction_funnel(spec: Mapping[str, object]) -> None:
    _validate_common(spec, {"snapshot_status", "stages", "unconsumed_reasons"})
    snapshot_status = _expect_enum(
        spec["snapshot_status"], {"complete", "partial", "failed"}, "snapshot_status"
    )
    stages = _expect_list(spec["stages"], "stages", maximum=5)
    _require_collection_state(spec, stages, "stages")
    if spec["data_status"] in {"available", "stale"} and len(stages) != 5:
        _fail("stages", "available/stale reaction lineage требует ровно пять стадий")
    reasons = _expect_string_list(
        spec["unconsumed_reasons"],
        "unconsumed_reasons",
        russian=True,
        maximum=20,
    )
    if spec["data_status"] in {"empty", "unavailable"} and reasons:
        _fail("unconsumed_reasons", "empty/unavailable не принимает lineage-причины")
    if spec["data_status"] == "unavailable" and snapshot_status != "failed":
        _fail("snapshot_status", "unavailable требует snapshot_status=failed")
    if spec["data_status"] != "unavailable" and snapshot_status == "failed":
        _fail("snapshot_status", "failed snapshot требует data_status=unavailable")
    if (
        snapshot_status == "partial"
        and not reasons
        and not spec.get("partial_reasons_ru")
    ):
        _fail("snapshot_status", "partial snapshot требует явную причину")
    counts: dict[str, int] = {}
    for index, raw_stage in enumerate(stages):
        path = f"stages[{index}]"
        stage = _expect_mapping(raw_stage, path)
        _expect_exact_fields(stage, required={"key", "label_ru", "count"}, path=path)
        expected_key = _REACTION_STAGE_KEYS[index]
        key = _expect_enum(stage["key"], set(_REACTION_STAGE_KEYS), f"{path}.key")
        if key != expected_key:
            _fail(f"{path}.key", f"ожидалась стадия {expected_key}")
        label = _expect_str(
            stage["label_ru"], f"{path}.label_ru", russian=True, max_length=120
        )
        if label != _REACTION_STAGE_LABELS[key]:
            _fail(
                f"{path}.label_ru",
                f"ожидалась фиксированная подпись {_REACTION_STAGE_LABELS[key]}",
            )
        counts[key] = _expect_int(stage["count"], f"{path}.count")
    if stages and counts["detected"] < counts["posts_resolved"]:
        _fail(
            "stages", "событий реакций не может быть меньше уникальных найденных постов"
        )
    if stages:
        ordered_counts = [counts[key] for key in _REACTION_STAGE_KEYS]
        if ordered_counts[0] == 0:
            _fail(
                "stages", "нулевое число реакций должно быть честным data_status=empty"
            )
        for index, count in enumerate(ordered_counts[:-1]):
            if count == 0 and any(later > 0 for later in ordered_counts[index + 1 :]):
                _fail(
                    "stages",
                    "после нулевой upstream-стадии downstream counts должны быть нулевыми",
                )
        if counts["signals_selected"] > 3:
            _fail(
                "stages",
                "Brief/editorial contract допускает не больше трех выбранных сигналов",
            )


def _render_reaction_funnel(
    spec: Mapping[str, object],
) -> tuple[str, bool, tuple[str, ...]]:
    if spec["data_status"] in {"empty", "unavailable"}:
        return (
            f"<p>{_e(_state_message('reaction_funnel', str(spec['data_status'])))}</p>",
            False,
            (),
        )
    stages = list(spec["stages"])
    unresolved_posts = int(stages[0]["count"]) - int(stages[1]["count"])
    rows = "".join(
        "<li><span>{label}</span><strong>{count}</strong><span>единиц стадии</span></li>".format(
            label=_e(_REACTION_STAGE_LABELS[str(stage["key"])]),
            count=_e(stage["count"]),
        )
        for stage in stages
    )
    reasons = list(spec["unconsumed_reasons"])
    reason_html = ""
    if reasons:
        reason_html = (
            "<h3>Почему часть событий не продолжила цепочку происхождения</h3>"
            '<ul class="irx-visual__list">'
            + "".join(f"<li>{_e(reason)}</li>" for reason in sorted(reasons))
            + "</ul>"
        )
    extra_partial = spec["snapshot_status"] == "partial"
    extra = ()
    snapshot_notice = ""
    if extra_partial:
        extra = ("Снимок связей реакций имеет статус partial.",)
        snapshot_notice = (
            '<div class="irx-visual__state irx-visual__state--partial" role="status">'
            "<strong>Снимок связей реакций частичный.</strong> Не все события удалось "
            "связать с последующими стадиями.</div>"
        )
    return (
        f"{snapshot_notice}"
        "<p>Показана цепочка происхождения событий; ширина блоков не является процентом конверсии.</p>"
        f"<p>Событий без найденного уникального поста: {unresolved_posts}. "
        "Изменения на последующих стадиях не трактуются как процентные потери.</p>"
        f'<ol class="irx-visual__flow">{rows}</ol>{reason_html}',
        extra_partial,
        extra,
    )


_RADAR_DECISIONS = {"investigate", "reject", "build_allowed", "unavailable"}
_RADAR_DECISION_LABELS = {
    "investigate": "Продолжить проверку",
    "reject": "Отклонить кандидата",
    "build_allowed": "Сборка разрешена Radar",
    "unavailable": "Решение недоступно",
}
_GATE_STATUS_LABELS = {
    "pass": "Пройден",
    "missing": "Не хватает данных",
    "blocked": "Заблокирован",
    "not_applicable": "Не применим",
}


def _validate_radar_gate(spec: Mapping[str, object]) -> None:
    fields = {
        "snapshot_status",
        "candidate_name",
        "dossier_status",
        "reader_decision",
        "gates",
        "candidate_evidence_count",
        "context_only_count",
        "missing_evidence",
        "next_validation_ru",
        "kill_criteria_ru",
    }
    _validate_common(spec, fields)
    snapshot = _expect_enum(
        spec["snapshot_status"], {"complete", "failed"}, "snapshot_status"
    )
    candidate = spec["candidate_name"]
    if candidate is not None:
        _expect_str(candidate, "candidate_name", max_length=180, allow_empty=True)
    dossier = _expect_enum(spec["dossier_status"], _RADAR_DECISIONS, "dossier_status")
    decision = _expect_enum(
        spec["reader_decision"], _RADAR_DECISIONS, "reader_decision"
    )
    gates = _expect_list(spec["gates"], "gates", maximum=30)
    evidence_count = _expect_int(
        spec["candidate_evidence_count"], "candidate_evidence_count"
    )
    _expect_int(spec["context_only_count"], "context_only_count")
    missing_evidence = _expect_string_list(
        spec["missing_evidence"], "missing_evidence", russian=True, maximum=30
    )
    allow_empty_guidance = spec["data_status"] in {"empty", "unavailable"}
    next_validation = _expect_str(
        spec["next_validation_ru"],
        "next_validation_ru",
        russian=True,
        max_length=500,
        allow_empty=allow_empty_guidance,
    )
    kill_criteria = _expect_str(
        spec["kill_criteria_ru"],
        "kill_criteria_ru",
        russian=True,
        max_length=500,
        allow_empty=allow_empty_guidance,
    )
    seen_keys: set[str] = set()
    gate_statuses: list[str] = []
    for index, raw_gate in enumerate(gates):
        path = f"gates[{index}]"
        gate = _expect_mapping(raw_gate, path)
        _expect_exact_fields(gate, required={"key", "status", "reason_ru"}, path=path)
        key = _expect_str(gate["key"], f"{path}.key", max_length=80)
        if key in seen_keys:
            _fail(f"{path}.key", "gate key должен быть уникальным")
        seen_keys.add(key)
        gate_statuses.append(
            _expect_enum(
                gate["status"],
                {"pass", "missing", "blocked", "not_applicable"},
                f"{path}.status",
            )
        )
        _expect_str(
            gate["reason_ru"], f"{path}.reason_ru", russian=True, max_length=400
        )
    status = str(spec["data_status"])
    if status == "empty":
        if snapshot != "complete" or candidate not in {None, ""} or gates:
            _fail("spec", "empty Radar требует успешный snapshot без кандидата и gates")
        if evidence_count or spec["context_only_count"]:
            _fail("spec", "empty Radar не должен содержать candidate/context counts")
        if decision != "unavailable" or dossier != "unavailable":
            _fail("reader_decision", "empty Radar не выдает решение по кандидату")
        if missing_evidence or next_validation or kill_criteria:
            _fail("spec", "empty Radar не должен сохранять candidate guidance")
    elif status == "unavailable":
        if snapshot != "failed" or candidate not in {None, ""} or gates:
            _fail(
                "spec", "unavailable Radar требует failed snapshot без candidate data"
            )
        if evidence_count or spec["context_only_count"]:
            _fail("spec", "unavailable Radar не должен подставлять нулевые данные")
        if decision != "unavailable" or dossier != "unavailable":
            _fail("reader_decision", "unavailable Radar требует unavailable decision")
        if missing_evidence or next_validation or kill_criteria:
            _fail("spec", "unavailable Radar не должен сохранять candidate guidance")
    else:
        if snapshot != "complete" or not candidate or not gates:
            _fail(
                "spec",
                "available/stale Radar требует complete snapshot, candidate и gates",
            )
        if decision == "unavailable" or dossier == "unavailable":
            _fail("reader_decision", "Radar с данными требует определенное решение")
        if decision == "build_allowed":
            if dossier != "build_allowed":
                _fail(
                    "reader_decision",
                    "renderer не может повысить investigate/reject dossier до build_allowed",
                )
            if evidence_count == 0:
                _fail(
                    "candidate_evidence_count", "context-only данные не разрешают build"
                )
            if any(
                status not in {"pass", "not_applicable"} for status in gate_statuses
            ):
                _fail(
                    "reader_decision",
                    "build_allowed несовместим с missing/blocked gate",
                )
        if dossier == "reject" and decision != "reject":
            _fail(
                "reader_decision",
                "reject dossier нельзя повысить до investigate/build_allowed",
            )


def _render_radar_gate(spec: Mapping[str, object]) -> tuple[str, bool, tuple[str, ...]]:
    if spec["data_status"] in {"empty", "unavailable"}:
        return (
            f"<p>{_e(_state_message('radar_gate', str(spec['data_status'])))}</p>",
            False,
            (),
        )
    decision = str(spec["reader_decision"])
    dossier = str(spec["dossier_status"])
    decision_class = (
        "confirmed"
        if decision == "build_allowed"
        else ("blocked" if decision == "reject" else "watch")
    )
    gates = sorted(spec["gates"], key=lambda gate: str(gate["key"]))
    gate_rows = "".join(
        '<li><span class="irx-visual__status irx-visual__status--{status}">{status_label}</span> '
        "<strong>Проверка {number}</strong>: {reason}</li>".format(
            status=_e(gate["status"]),
            status_label=_e(_GATE_STATUS_LABELS[str(gate["status"])]),
            number=index + 1,
            reason=_e(gate["reason_ru"]),
        )
        for index, gate in enumerate(gates)
    )
    missing = list(spec["missing_evidence"])
    missing_html = (
        '<h3>Недостающие доказательства</h3><ul class="irx-visual__list">'
        + "".join(f"<li>{_e(item)}</li>" for item in sorted(missing))
        + "</ul>"
        if missing
        else "<p>Явно перечисленных пробелов доказательств нет.</p>"
    )
    return (
        f"<p><strong>Кандидат:</strong> {_e(spec['candidate_name'])}</p>"
        f"<p><strong>Статус досье:</strong> {_e(_RADAR_DECISION_LABELS[dossier])}.</p>"
        f"<p><strong>Решение для читателя:</strong> "
        f'<span class="irx-visual__status irx-visual__status--{decision_class}">'
        f"{_e(_RADAR_DECISION_LABELS[decision])}</span></p>"
        '<div class="irx-visual__split">'
        '<section class="irx-visual__card"><h3>Доказательства кандидата</h3>'
        f"<p><strong>{_e(spec['candidate_evidence_count'])}</strong> записей заполняют досье и проверки Radar.</p>"
        '</section><section class="irx-visual__card"><h3>Только контекст</h3>'
        f"<p><strong>{_e(spec['context_only_count'])}</strong> записей не заполняют проверки Radar.</p>"
        "</section></div>"
        f'<h3>Проверки Radar</h3><ul class="irx-visual__list">{gate_rows}</ul>{missing_html}'
        f"<p><strong>Следующая проверка:</strong> {_e(spec['next_validation_ru'])}</p>"
        f"<p><strong>Критерий остановки:</strong> {_e(spec['kill_criteria_ru'])}</p>",
        False,
        (),
    )


_PROJECT_STATUSES = {
    "confirmed",
    "watch",
    "rejected_overlap",
    "learning_only",
    "existing_context",
}
_PROJECT_STATUS_LABELS = {
    "confirmed": "Подтверждено",
    "watch": "Наблюдать",
    "rejected_overlap": "Отклонено: уже покрыто",
    "learning_only": "Только для обучения",
    "existing_context": "Существующий контекст",
}


def _validate_project_impact(spec: Mapping[str, object]) -> None:
    _validate_common(spec, {"items"})
    items = _expect_list(spec["items"], "items", maximum=30)
    _require_collection_state(spec, items, "items")
    confirmed = 0
    keys: set[tuple[str, str]] = set()
    for index, raw_item in enumerate(items):
        path = f"items[{index}]"
        item = _expect_mapping(raw_item, path)
        _expect_exact_fields(
            item,
            required={
                "project_name",
                "signal_ref",
                "signal_label_ru",
                "suggested_change_ru",
                "affected_component",
                "likely_files",
                "effort",
                "confidence",
                "acceptance_criteria",
                "risk_ru",
                "evidence_refs",
                "status",
            },
            path=path,
        )
        project = _expect_str(
            item["project_name"], f"{path}.project_name", max_length=160
        )
        signal = _validate_reference(item["signal_ref"], f"{path}.signal_ref")
        if (project, signal) in keys:
            _fail(path, "project_name + signal_ref должны быть уникальными")
        keys.add((project, signal))
        _expect_str(
            item["signal_label_ru"],
            f"{path}.signal_label_ru",
            russian=True,
            max_length=240,
        )
        _expect_str(
            item["suggested_change_ru"],
            f"{path}.suggested_change_ru",
            russian=True,
            max_length=500,
        )
        _expect_str(
            item["affected_component"], f"{path}.affected_component", max_length=180
        )
        files = _expect_list(item["likely_files"], f"{path}.likely_files", maximum=20)
        if not files:
            _fail(f"{path}.likely_files", "нужен хотя бы один конкретный файл")
        for file_index, file_path in enumerate(files):
            _validate_local_path(file_path, f"{path}.likely_files[{file_index}]")
        _expect_str(item["effort"], f"{path}.effort", russian=True, max_length=120)
        _expect_enum(item["confidence"], _CONFIDENCE, f"{path}.confidence")
        _expect_string_list(
            item["acceptance_criteria"],
            f"{path}.acceptance_criteria",
            russian=True,
            maximum=12,
            allow_empty=False,
        )
        _expect_str(item["risk_ru"], f"{path}.risk_ru", russian=True, max_length=500)
        evidence_refs = _expect_list(
            item["evidence_refs"], f"{path}.evidence_refs", maximum=30
        )
        if not evidence_refs:
            _fail(f"{path}.evidence_refs", "проектная связь требует evidence ref")
        validated_evidence = [
            _validate_reference(ref, f"{path}.evidence_refs[{ref_index}]")
            for ref_index, ref in enumerate(evidence_refs)
        ]
        if len(validated_evidence) != len(set(validated_evidence)):
            _fail(f"{path}.evidence_refs", "повторяющиеся evidence refs запрещены")
        status = _expect_enum(item["status"], _PROJECT_STATUSES, f"{path}.status")
        if status == "confirmed":
            confirmed += 1
    if confirmed > 2:
        _fail("items", "в одном компоненте разрешено не больше двух confirmed действий")


def _render_project_impact(
    spec: Mapping[str, object],
) -> tuple[str, bool, tuple[str, ...]]:
    if spec["data_status"] in {"empty", "unavailable"}:
        return (
            f"<p>{_e(_state_message('project_impact', str(spec['data_status'])))}</p>",
            False,
            (),
        )
    status_rank = {
        "confirmed": 0,
        "watch": 1,
        "learning_only": 2,
        "existing_context": 3,
        "rejected_overlap": 4,
    }
    items = sorted(
        spec["items"],
        key=lambda item: (
            status_rank[str(item["status"])],
            str(item["project_name"]).casefold(),
            str(item["signal_ref"]),
        ),
    )
    rows: list[str] = []
    confirmed_count = sum(item["status"] == "confirmed" for item in items)
    for item in items:
        actionable = item["status"] == "confirmed"
        files = ", ".join(
            f"<code>{_e(path)}</code>" for path in sorted(item["likely_files"])
        )
        criteria = "".join(
            f"<li>{_e(criterion)}</li>"
            for criterion in sorted(item["acceptance_criteria"])
        )
        rows.append(
            f'<tr data-actionable="{str(actionable).lower()}">'
            f'<td><span class="irx-visual__mobile-label">Проект</span>{_e(item["project_name"])}</td>'
            f'<td><span class="irx-visual__mobile-label">Статус</span>'
            f'<span class="irx-visual__status irx-visual__status--'
            f'{"confirmed" if actionable else "neutral"}">'
            f"{_e(_PROJECT_STATUS_LABELS[str(item['status'])])}</span></td>"
            f'<td><span class="irx-visual__mobile-label">Изменение</span>'
            f"<strong>Сигнал:</strong> {_e(item['signal_label_ru'])}<br>"
            f"{_e(item['suggested_change_ru'])}<br><strong>Компонент:</strong> "
            f"{_e(item['affected_component'])}</td>"
            f'<td><span class="irx-visual__mobile-label">Детали</span>'
            f"<strong>Файлы:</strong> {files}<br><strong>Оценка:</strong> {_e(item['effort'])}"
            f"<br><strong>Уверенность:</strong> {_e(_CONFIDENCE_LABELS[str(item['confidence'])])}"
            f"<br><strong>Связанных доказательств:</strong> {len(item['evidence_refs'])}"
            f"<br><strong>Риск:</strong> {_e(item['risk_ru'])}"
            f"<br><strong>Критерии:</strong><ul>{criteria}</ul></td></tr>"
        )
    confirmed_notice = (
        ""
        if confirmed_count
        else '<p class="irx-visual__state"><strong>Подтвержденного влияния на активные '
        "проекты нет.</strong> Ниже сохранены только наблюдения и неактивные состояния.</p>"
    )
    return (
        confirmed_notice
        + '<div class="irx-visual__table-wrap"><table class="irx-visual__project">'
        '<thead><tr><th scope="col">Проект</th><th scope="col">Статус</th>'
        '<th scope="col">Предложение</th><th scope="col">Проверяемые детали</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>",
        False,
        (),
    )


_GRAPH_STATUSES = {"growing", "watch", "stale", "contradicted"}
_GRAPH_STATUS_LABELS = {
    "growing": "Растет",
    "watch": "Наблюдать",
    "stale": "Устаревает",
    "contradicted": "Есть противоречия",
}
_GRAPH_RELATIONS = {"supports", "depends_on", "contradicts", "converges_with"}
_GRAPH_RELATION_LABELS = {
    "supports": "поддерживает",
    "depends_on": "зависит от",
    "contradicts": "противоречит",
    "converges_with": "сходится с",
}


def _validate_knowledge_graph(spec: Mapping[str, object]) -> None:
    _validate_common(spec, {"encoding", "nodes", "edges", "audit_explorer_path"})
    _validate_local_path(spec["audit_explorer_path"], "audit_explorer_path")
    encoding = _expect_mapping(spec["encoding"], "encoding")
    _expect_exact_fields(
        encoding,
        required={"node_size", "node_border", "node_accent"},
        path="encoding",
    )
    expected_encoding = {
        "node_size": "evidence_volume",
        "node_border": "evidence_maturity",
        "node_accent": "operator_interest",
    }
    if dict(encoding) != expected_encoding:
        _fail("encoding", "v1 требует evidence volume / maturity / operator interest")
    nodes = _expect_list(spec["nodes"], "nodes", maximum=100)
    edges = _expect_list(spec["edges"], "edges", maximum=300)
    _require_collection_state(spec, nodes, "nodes")
    if spec["data_status"] in {"empty", "unavailable"} and edges:
        _fail("edges", "empty/unavailable graph не принимает edges")
    node_ids: set[str] = set()
    for index, raw_node in enumerate(nodes):
        path = f"nodes[{index}]"
        node = _expect_mapping(raw_node, path)
        _expect_exact_fields(
            node,
            required={
                "canonical_thread_id",
                "title_ru",
                "status",
                "evidence_volume",
                "evidence_maturity",
                "operator_interest_score",
                "display_priority",
            },
            path=path,
        )
        node_id = _expect_str(
            node["canonical_thread_id"], f"{path}.canonical_thread_id", max_length=160
        )
        if node_id in node_ids:
            _fail(
                f"{path}.canonical_thread_id",
                "canonical thread id должен быть уникальным",
            )
        node_ids.add(node_id)
        _expect_str(node["title_ru"], f"{path}.title_ru", russian=True, max_length=260)
        _expect_enum(node["status"], _GRAPH_STATUSES, f"{path}.status")
        _expect_int(node["evidence_volume"], f"{path}.evidence_volume")
        _expect_enum(node["evidence_maturity"], _MATURITY, f"{path}.evidence_maturity")
        score = _expect_number(
            node["operator_interest_score"], f"{path}.operator_interest_score"
        )
        if score > 1:
            _fail(
                f"{path}.operator_interest_score", "score должен быть в диапазоне 0..1"
            )
        _expect_int(node["display_priority"], f"{path}.display_priority")
    edge_keys: set[tuple[str, str, str]] = set()
    for index, raw_edge in enumerate(edges):
        path = f"edges[{index}]"
        edge = _expect_mapping(raw_edge, path)
        _expect_exact_fields(
            edge,
            required={
                "source_thread_id",
                "target_thread_id",
                "relation",
                "weight",
                "evidence_refs",
            },
            path=path,
        )
        source = _expect_str(
            edge["source_thread_id"], f"{path}.source_thread_id", max_length=160
        )
        target = _expect_str(
            edge["target_thread_id"], f"{path}.target_thread_id", max_length=160
        )
        relation = _expect_enum(edge["relation"], _GRAPH_RELATIONS, f"{path}.relation")
        if source == target:
            _fail(path, "self-edge запрещен")
        if source not in node_ids or target not in node_ids:
            _fail(path, "edge ссылается на неизвестный node")
        edge_key = (source, target, relation)
        if edge_key in edge_keys:
            _fail(path, "дублирующий edge запрещен")
        edge_keys.add(edge_key)
        _expect_int(edge["weight"], f"{path}.weight", minimum=1)
        refs = _expect_list(edge["evidence_refs"], f"{path}.evidence_refs", maximum=30)
        if not refs:
            _fail(f"{path}.evidence_refs", "typed relation требует evidence refs")
        validated = [
            _validate_reference(ref, f"{path}.evidence_refs[{ref_index}]")
            for ref_index, ref in enumerate(refs)
        ]
        if len(validated) != len(set(validated)):
            _fail(f"{path}.evidence_refs", "повторяющиеся refs запрещены")


def _truncate_label(text: object, limit: int = 18) -> str:
    value = str(text)
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _fmt(value: float) -> str:
    if value == 0:
        return "0"
    text = f"{value:.2f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _graph_selection(
    spec: Mapping[str, object],
) -> tuple[list[Mapping[str, object]], int]:
    ordered = sorted(
        spec["nodes"],
        key=lambda node: (
            -int(node["display_priority"]),
            str(node["canonical_thread_id"]),
        ),
    )
    selected = ordered[:12]
    return sorted(selected, key=lambda node: str(node["canonical_thread_id"])), max(
        0, len(ordered) - len(selected)
    )


def _render_knowledge_graph(
    spec: Mapping[str, object],
) -> tuple[str, bool, tuple[str, ...]]:
    audit_link = (
        f'<a href="{_e(spec["audit_explorer_path"])}" '
        'aria-label="Открыть подробный аудит канонических тем">Открыть Audit Explorer</a>'
    )
    if spec["data_status"] == "empty":
        return (
            f"<p>{_e(_state_message('knowledge_graph', 'empty'))} {audit_link}.</p>",
            False,
            (),
        )
    if spec["data_status"] == "unavailable":
        return (
            f"<p>{_e(_state_message('knowledge_graph', 'unavailable'))}</p>",
            False,
            (),
        )
    nodes, excluded = _graph_selection(spec)
    id_to_local = {
        str(node["canonical_thread_id"]): f"{spec['component_id']}-n{index + 1}"
        for index, node in enumerate(nodes)
    }
    local_to_node = {local: node for node, local in zip(nodes, id_to_local.values())}
    positions: dict[str, tuple[int, int]] = {}
    for index, node in enumerate(nodes):
        local = id_to_local[str(node["canonical_thread_id"])]
        positions[local] = (55 + (index % 3) * 300, 55 + (index // 3) * 150)
    rows = max(1, math.ceil(len(nodes) / 3))
    height = 80 + rows * 150
    selected_ids = set(id_to_local)
    visible_edges = sorted(
        [
            edge
            for edge in spec["edges"]
            if edge["source_thread_id"] in selected_ids
            and edge["target_thread_id"] in selected_ids
        ],
        key=lambda edge: (
            str(edge["source_thread_id"]),
            str(edge["target_thread_id"]),
            str(edge["relation"]),
        ),
    )
    line_svg: list[str] = []
    for edge in visible_edges:
        source_local = id_to_local[str(edge["source_thread_id"])]
        target_local = id_to_local[str(edge["target_thread_id"])]
        sx, sy = positions[source_local]
        tx, ty = positions[target_local]
        dash = (
            ' stroke-dasharray="7 5"'
            if edge["relation"] in {"contradicts", "depends_on"}
            else ""
        )
        line_svg.append(
            f'<line x1="{sx + 125}" y1="{sy + 42}" x2="{tx + 125}" y2="{ty + 42}" '
            f'stroke="#475569" stroke-width="{min(5, 1 + int(edge["weight"]))}"{dash} '
            f'marker-end="url(#{_e(spec["component_id"])}-graph-arrow)" />'
        )
    max_volume = max((int(node["evidence_volume"]) for node in nodes), default=0)
    node_svg: list[str] = []
    clip_defs: list[str] = []
    node_list: list[str] = []
    maturity_order = [
        "single_source",
        "repeated_signal",
        "multi_channel",
        "primary_verified",
        "externally_corroborated",
        "decision_grade",
    ]
    for local, node in local_to_node.items():
        x, y = positions[local]
        clip_id = f"{local}-text-clip"
        clip_defs.append(
            f'<clipPath id="{clip_id}"><rect x="{x + 55}" y="{y + 8}" '
            'width="185" height="50" /></clipPath>'
        )
        volume = int(node["evidence_volume"])
        radius = 0 if max_volume == 0 else round(22 * volume / max_volume, 2)
        maturity_index = maturity_order.index(str(node["evidence_maturity"]))
        dash = "" if maturity_index >= 3 else ' stroke-dasharray="7 4"'
        interest_width = round(100 * float(node["operator_interest_score"]), 2)
        node_svg.append(
            f'<a href="#{local}-details" aria-label="Перейти к описанию темы: '
            f'{_e(node["title_ru"])}"><g id="{local}" role="group">'
            f'<rect x="{x}" y="{y}" width="250" height="84" rx="8" fill="#ffffff" '
            f'stroke="#1d4ed8" stroke-width="{2 + (maturity_index // 2)}"{dash} />'
            f'<circle cx="{x + 28}" cy="{y + 28}" r="{_fmt(radius)}" fill="#bfdbfe" '
            'stroke="#1d4ed8" aria-hidden="true" />'
            f'<text x="{x + 58}" y="{y + 27}" font-size="14" '
            f'clip-path="url(#{clip_id})">{_e(_truncate_label(node["title_ru"]))}</text>'
            f'<text x="{x + 58}" y="{y + 49}" font-size="12" '
            f'clip-path="url(#{clip_id})">'
            f"{_e(_GRAPH_STATUS_LABELS[str(node['status'])])}; фактов: {volume}</text>"
            f'<rect x="{x + 58}" y="{y + 61}" width="{_fmt(interest_width)}" height="6" '
            'fill="#be123c" aria-hidden="true" />'
            "</g></a>"
        )
        node_list.append(
            f'<li id="{local}-details"><strong>{_e(node["title_ru"])}</strong>: '
            f"{_e(_GRAPH_STATUS_LABELS[str(node['status'])])}; "
            f"объем доказательств — {volume}; зрелость — "
            f"{_e(_MATURITY_LABELS[str(node['evidence_maturity'])])}; "
            f"интерес оператора — {_fmt(float(node['operator_interest_score']))}.</li>"
        )
    relation_rows: list[str] = []
    for edge in visible_edges:
        source_node = nodes[
            next(
                index
                for index, node in enumerate(nodes)
                if node["canonical_thread_id"] == edge["source_thread_id"]
            )
        ]
        target_node = nodes[
            next(
                index
                for index, node in enumerate(nodes)
                if node["canonical_thread_id"] == edge["target_thread_id"]
            )
        ]
        relation_rows.append(
            "<li><strong>{source}</strong> {relation} <strong>{target}</strong>; "
            "вес связи: {weight}; ссылок на доказательства: {refs}.</li>".format(
                source=_e(source_node["title_ru"]),
                relation=_e(_GRAPH_RELATION_LABELS[str(edge["relation"])]),
                target=_e(target_node["title_ru"]),
                weight=_e(edge["weight"]),
                refs=len(edge["evidence_refs"]),
            )
        )
    graph_title_id = f"{spec['component_id']}-svg-title"
    graph_desc_id = f"{spec['component_id']}-svg-desc"
    svg = (
        '<div class="irx-visual__canvas" tabindex="0" aria-label="Прокручиваемый граф тем">'
        f'<svg class="irx-visual__graph-svg" viewBox="0 0 960 {height}" role="img" '
        f'aria-labelledby="{_e(graph_title_id)} {_e(graph_desc_id)}" '
        f'preserveAspectRatio="xMinYMin meet">'
        f'<title id="{_e(graph_title_id)}">Карта связей канонических тем</title>'
        f'<desc id="{_e(graph_desc_id)}">Размерный маркер показывает объем доказательств; '
        "граница — зрелость; красная полоса — интерес оператора; пунктир — зависимость или противоречие.</desc>"
        f'<defs><marker id="{_e(spec["component_id"])}-graph-arrow" viewBox="0 0 10 10" '
        'refX="9" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" '
        f'fill="#475569" /></marker>{"".join(clip_defs)}</defs>'
        f"{''.join(line_svg)}{''.join(node_svg)}</svg></div>"
    )
    exclusion = (
        f'<p class="irx-visual__state irx-visual__state--partial">'
        f"По детерминированному лимиту показано 12 тем; исключено: {excluded}.</p>"
        if excluded
        else ""
    )
    relations = (
        "".join(relation_rows)
        or "<li>Между показанными темами нет доказанных связей.</li>"
    )
    return (
        "<p>Легенда: размерный круг — объем доказательств; сплошная/пунктирная граница — "
        "зрелость; красная полоса — отдельный сигнал интереса оператора.</p>"
        f"{exclusion}{svg}<h3>Темы</h3>"
        f'<ol class="irx-visual__list">{"".join(node_list)}</ol>'
        f'<div class="irx-visual__relations"><h3>Доказанные отношения</h3>'
        f'<ul class="irx-visual__list">{relations}</ul></div>'
        f"<p>{audit_link} для полной истории происхождения и исключенных тем.</p>",
        bool(excluded),
        (f"Из графа по лимиту исключено тем: {excluded}.",) if excluded else (),
    )


_TIMELINE_EVENT_TYPES = {"merge", "split", "milestone", "contradiction"}
_TIMELINE_EVENT_LABELS = {
    "merge": "слияние",
    "split": "разделение",
    "milestone": "важное событие",
    "contradiction": "противоречие",
}


def _validate_thread_timeline(spec: Mapping[str, object]) -> None:
    _validate_common(spec, {"weeks", "series"})
    weeks = _expect_list(spec["weeks"], "weeks", maximum=12)
    week_values: list[str] = []
    week_starts: list[datetime] = []
    for index, week in enumerate(weeks):
        text = _expect_str(week, f"weeks[{index}]", max_length=8)
        if not _WEEK_RE.fullmatch(text):
            _fail(f"weeks[{index}]", "ожидался ISO week")
        week_values.append(text)
        year_text, week_text = text.split("-W", 1)
        try:
            week_starts.append(
                datetime.fromisocalendar(int(year_text), int(week_text), 1)
            )
        except ValueError as exc:
            raise ReportVisualValidationError(
                f"weeks[{index}]: недопустимая ISO-неделя"
            ) from exc
    if week_values != sorted(set(week_values)):
        _fail("weeks", "weeks должны быть уникальны и строго возрастающими")
    if any(
        current - previous != timedelta(weeks=1)
        for previous, current in zip(week_starts, week_starts[1:])
    ):
        _fail("weeks", "timeline weeks должны идти без пропусков")
    series = _expect_list(spec["series"], "series", maximum=30)
    _require_collection_state(spec, series, "series")
    if spec["data_status"] in {"available", "stale"} and not weeks:
        _fail("weeks", "timeline с данными требует weeks")
    if spec["data_status"] == "empty" and len(weeks) >= 12:
        _fail("weeks", "empty timeline должен содержать меньше 12 доступных снимков")
    if spec["data_status"] in {"available", "empty"} and weeks:
        if week_values[-1] != spec["reporting_week"]:
            _fail("weeks", "current timeline должен завершаться reporting_week")
    if spec["data_status"] == "stale" and weeks:
        if week_values[-1] != spec["stale_from_period"]:
            _fail("weeks", "stale timeline должен завершаться stale_from_period")
    if (
        spec["data_status"] == "available"
        and len(weeks) < 12
        and not spec.get("partial_reasons_ru")
    ):
        _fail(
            "partial_reasons_ru",
            "timeline короче 12 недель требует явную partial-причину",
        )
    if spec["data_status"] == "unavailable" and weeks:
        _fail("weeks", "unavailable timeline не должен подставлять период")
    seen_ids: set[str] = set()
    for index, raw_series in enumerate(series):
        path = f"series[{index}]"
        item = _expect_mapping(raw_series, path)
        _expect_exact_fields(
            item,
            required={
                "canonical_thread_id",
                "title_ru",
                "momentum",
                "evidence_count",
                "events",
            },
            path=path,
        )
        thread_id = _expect_str(
            item["canonical_thread_id"], f"{path}.canonical_thread_id", max_length=160
        )
        if thread_id in seen_ids:
            _fail(f"{path}.canonical_thread_id", "thread id должен быть уникальным")
        seen_ids.add(thread_id)
        _expect_str(item["title_ru"], f"{path}.title_ru", russian=True, max_length=260)
        momentum = _expect_list(item["momentum"], f"{path}.momentum", maximum=12)
        evidence = _expect_list(
            item["evidence_count"], f"{path}.evidence_count", maximum=12
        )
        if len(momentum) != len(weeks) or len(evidence) != len(weeks):
            _fail(path, "momentum/evidence_count должны совпадать с длиной weeks")
        for value_index, value in enumerate(momentum):
            if value is not None:
                _expect_number(value, f"{path}.momentum[{value_index}]")
        if momentum and all(value is None for value in momentum):
            _fail(
                f"{path}.momentum",
                "ряд без единого наблюдения нельзя показывать как доступный sparkline",
            )
        for value_index, value in enumerate(evidence):
            if value is not None:
                _expect_int(value, f"{path}.evidence_count[{value_index}]")
        events = _expect_list(item["events"], f"{path}.events", maximum=50)
        event_keys: set[tuple[str, str, str]] = set()
        for event_index, raw_event in enumerate(events):
            event_path = f"{path}.events[{event_index}]"
            event = _expect_mapping(raw_event, event_path)
            _expect_exact_fields(
                event, required={"week", "type", "label_ru"}, path=event_path
            )
            event_week = _expect_str(event["week"], f"{event_path}.week", max_length=8)
            if event_week not in week_values:
                _fail(f"{event_path}.week", "event week отсутствует в timeline")
            event_type = _expect_enum(
                event["type"], _TIMELINE_EVENT_TYPES, f"{event_path}.type"
            )
            label = _expect_str(
                event["label_ru"],
                f"{event_path}.label_ru",
                russian=True,
                max_length=240,
            )
            key = (event_week, event_type, label)
            if key in event_keys:
                _fail(event_path, "дублирующее событие запрещено")
            event_keys.add(key)


def _polyline_segments(values: Sequence[object], scale_max: float) -> list[str]:
    if not values:
        return []
    x_step = 520 / max(1, len(values) - 1)
    segments: list[list[str]] = []
    current: list[str] = []
    for index, raw_value in enumerate(values):
        if raw_value is None:
            if current:
                segments.append(current)
                current = []
            continue
        value = float(raw_value)
        x = 40 + x_step * index
        y = 80 if scale_max == 0 else 80 - (60 * value / scale_max)
        current.append(f"{_fmt(x)},{_fmt(y)}")
    if current:
        segments.append(current)
    return [" ".join(segment) for segment in segments]


def _trend_sentence(values: Sequence[object]) -> str:
    observed = [float(value) for value in values if value is not None]
    if not observed:
        return "Динамика неизвестна: все значения отсутствуют."
    if len(observed) == 1:
        return f"Доступна одна точка: {_fmt(observed[0])}."
    delta = observed[-1] - observed[0]
    direction = (
        "выросла" if delta > 0 else ("снизилась" if delta < 0 else "не изменилась")
    )
    return (
        f"Динамика {direction}: первая доступная точка {_fmt(observed[0])}, "
        f"последняя {_fmt(observed[-1])}."
    )


def _render_thread_timeline(
    spec: Mapping[str, object],
) -> tuple[str, bool, tuple[str, ...]]:
    if spec["data_status"] in {"empty", "unavailable"}:
        range_text = ""
        if spec["data_status"] == "empty" and spec["weeks"]:
            range_text = (
                f" Доступный диапазон: {_e(spec['weeks'][0])}–{_e(spec['weeks'][-1])}."
            )
        return (
            f"<p>{_e(_state_message('thread_timeline', str(spec['data_status'])))}{range_text}</p>",
            False,
            (),
        )
    weeks = list(spec["weeks"])
    series = sorted(spec["series"], key=lambda item: str(item["canonical_thread_id"]))
    scale_max = max(
        (
            float(value)
            for item in series
            for value in item["momentum"]
            if value is not None
        ),
        default=0.0,
    )
    blocks: list[str] = []
    for index, item in enumerate(series):
        title_id = f"{spec['component_id']}-spark-{index + 1}-title"
        desc_id = f"{spec['component_id']}-spark-{index + 1}-desc"
        segments = _polyline_segments(item["momentum"], scale_max)
        paths = "".join(
            f'<polyline points="{points}" fill="none" stroke="#1d4ed8" stroke-width="3" />'
            for points in segments
        )
        observed_points = []
        for value_index, value in enumerate(item["momentum"]):
            if value is not None:
                x = 40 + (520 / max(1, len(weeks) - 1)) * value_index
                y = 80 if scale_max == 0 else 80 - (60 * float(value) / scale_max)
                stroke = "#166534" if value == 0 else "#1d4ed8"
                observed_points.append(
                    f'<circle cx="{_fmt(x)}" cy="{_fmt(y)}" r="4" fill="#ffffff" '
                    f'stroke="{stroke}" stroke-width="2" />'
                )
        rows: list[str] = []
        for week, momentum, evidence in zip(
            weeks, item["momentum"], item["evidence_count"]
        ):
            momentum_text = "нет данных" if momentum is None else _fmt(float(momentum))
            evidence_text = "нет данных" if evidence is None else str(evidence)
            rows.append(
                f'<tr><th scope="row">{_e(week)}</th><td>{_e(momentum_text)}</td>'
                f"<td>{_e(evidence_text)}</td></tr>"
            )
        events = sorted(
            item["events"],
            key=lambda event: (event["week"], event["type"], event["label_ru"]),
        )
        event_html = (
            '<h4>События</h4><ul class="irx-visual__list">'
            + "".join(
                f"<li>{_e(event['week'])} — "
                f"{_e(_TIMELINE_EVENT_LABELS[str(event['type'])])}: "
                f"{_e(event['label_ru'])}</li>"
                for event in events
            )
            + "</ul>"
            if events
            else "<p>За диапазон нет отмеченных событий изменения темы.</p>"
        )
        blocks.append(
            '<section class="irx-visual__spark">'
            f"<h3>{_e(item['title_ru'])}</h3><p>{_e(_trend_sentence(item['momentum']))}</p>"
            f'<svg viewBox="0 0 600 100" role="img" '
            f'aria-labelledby="{_e(title_id)} {_e(desc_id)}">'
            f'<title id="{_e(title_id)}">Динамика темы {_e(item["title_ru"])}</title>'
            f'<desc id="{_e(desc_id)}">Общая шкала от нуля до {_fmt(scale_max)}; '
            "разрыв линии означает отсутствие данных, точка на нижней линии означает ноль.</desc>"
            '<line x1="40" y1="80" x2="560" y2="80" stroke="#475569" stroke-width="1" />'
            f"{paths}{''.join(observed_points)}</svg>"
            '<div class="irx-visual__table-wrap"><table><thead><tr><th scope="col">Неделя</th>'
            '<th scope="col">Импульс</th><th scope="col">Доказательства</th></tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div>{event_html}</section>"
        )
    return (
        f"<p>Все ряды используют общую шкалу от 0 до {_fmt(scale_max)}. "
        "Разрыв линии — пропуск, нижняя точка — наблюдаемый ноль.</p>"
        f"{''.join(blocks)}",
        False,
        (),
    )


def _validate_source_thread_heatmap(spec: Mapping[str, object]) -> None:
    _validate_common(spec, {"value", "sources", "threads", "cells"})
    _expect_enum(
        spec["value"],
        {"mention_count", "independent_support_count"},
        "value",
    )
    sources = _expect_list(spec["sources"], "sources", maximum=40)
    threads = _expect_list(spec["threads"], "threads", maximum=40)
    cells = _expect_list(spec["cells"], "cells", maximum=800)
    _require_collection_state(spec, sources, "sources")
    _require_collection_state(spec, threads, "threads")
    if spec["data_status"] in {"empty", "unavailable"} and cells:
        _fail("cells", "empty/unavailable heatmap не принимает cells")
    source_ids: set[str] = set()
    source_status: dict[str, str] = {}
    for index, raw_source in enumerate(sources):
        path = f"sources[{index}]"
        source = _expect_mapping(raw_source, path)
        _expect_exact_fields(
            source,
            required={
                "source_id",
                "label",
                "independence_group",
                "classification_status",
            },
            path=path,
        )
        source_id = _expect_str(
            source["source_id"], f"{path}.source_id", max_length=160
        )
        if source_id in source_ids:
            _fail(f"{path}.source_id", "source id должен быть уникальным")
        source_ids.add(source_id)
        _expect_str(source["label"], f"{path}.label", max_length=220)
        _expect_str(
            source["independence_group"], f"{path}.independence_group", max_length=160
        )
        source_status[source_id] = _expect_enum(
            source["classification_status"],
            {"available", "unavailable"},
            f"{path}.classification_status",
        )
    if any(status == "unavailable" for status in source_status.values()):
        if not spec.get("partial_reasons_ru"):
            _fail(
                "partial_reasons_ru",
                "недоступная классификация источника требует явную partial-причину",
            )
    thread_ids: set[str] = set()
    for index, raw_thread in enumerate(threads):
        path = f"threads[{index}]"
        thread = _expect_mapping(raw_thread, path)
        _expect_exact_fields(
            thread, required={"canonical_thread_id", "title_ru"}, path=path
        )
        thread_id = _expect_str(
            thread["canonical_thread_id"], f"{path}.canonical_thread_id", max_length=160
        )
        if thread_id in thread_ids:
            _fail(f"{path}.canonical_thread_id", "thread id должен быть уникальным")
        thread_ids.add(thread_id)
        _expect_str(
            thread["title_ru"], f"{path}.title_ru", russian=True, max_length=260
        )
    cell_keys: set[tuple[str, str]] = set()
    for index, raw_cell in enumerate(cells):
        path = f"cells[{index}]"
        cell = _expect_mapping(raw_cell, path)
        _expect_exact_fields(
            cell,
            required={
                "source_id",
                "canonical_thread_id",
                "mention_count",
                "independent_support_count",
                "evidence_refs",
            },
            path=path,
        )
        source_id = _expect_str(cell["source_id"], f"{path}.source_id", max_length=160)
        thread_id = _expect_str(
            cell["canonical_thread_id"], f"{path}.canonical_thread_id", max_length=160
        )
        if source_id not in source_ids or thread_id not in thread_ids:
            _fail(path, "cell ссылается на неизвестный source/thread")
        key = (source_id, thread_id)
        if key in cell_keys:
            _fail(path, "дублирующая cell запрещена")
        cell_keys.add(key)
        if source_status[source_id] == "unavailable":
            _fail(path, "нельзя подставлять cell для неклассифицированного source")
        mentions = _expect_int(cell["mention_count"], f"{path}.mention_count")
        independent = _expect_int(
            cell["independent_support_count"], f"{path}.independent_support_count"
        )
        if independent > mentions:
            _fail(path, "independent support не может превышать mentions")
        refs = _expect_list(cell["evidence_refs"], f"{path}.evidence_refs", maximum=50)
        if (mentions or independent) and not refs:
            _fail(f"{path}.evidence_refs", "ненулевая cell требует evidence refs")
        validated = [
            _validate_reference(ref, f"{path}.evidence_refs[{ref_index}]")
            for ref_index, ref in enumerate(refs)
        ]
        if len(validated) != len(set(validated)):
            _fail(f"{path}.evidence_refs", "повторяющиеся refs запрещены")


def _render_source_thread_heatmap(
    spec: Mapping[str, object],
) -> tuple[str, bool, tuple[str, ...]]:
    if spec["data_status"] in {"empty", "unavailable"}:
        return (
            f"<p>{_e(_state_message('source_thread_heatmap', str(spec['data_status'])))}</p>",
            False,
            (),
        )
    sources = sorted(
        spec["sources"],
        key=lambda source: (str(source["label"]).casefold(), str(source["source_id"])),
    )
    threads = sorted(
        spec["threads"],
        key=lambda thread: (
            str(thread["title_ru"]).casefold(),
            str(thread["canonical_thread_id"]),
        ),
    )
    cells = {
        (str(cell["source_id"]), str(cell["canonical_thread_id"])): cell
        for cell in spec["cells"]
    }
    value_key = str(spec["value"])
    value_label = (
        "число независимых подтверждений"
        if value_key == "independent_support_count"
        else "число упоминаний"
    )
    max_value = max((int(cell[value_key]) for cell in spec["cells"]), default=0)
    head = "".join(
        f'<th scope="col">{_e(thread["title_ru"])}</th>' for thread in threads
    )
    body_rows: list[str] = []
    totals = {str(thread["canonical_thread_id"]): 0 for thread in threads}
    for source in sources:
        source_id = str(source["source_id"])
        row_cells: list[str] = []
        for thread in threads:
            thread_id = str(thread["canonical_thread_id"])
            if source["classification_status"] == "unavailable":
                row_cells.append(
                    '<td class="irx-visual__unknown"><strong>Неизвестно.</strong> '
                    "Классификация источника недоступна.</td>"
                )
                continue
            cell = cells.get((source_id, thread_id))
            mentions = int(cell["mention_count"]) if cell else 0
            independent = int(cell["independent_support_count"]) if cell else 0
            value = (
                independent if value_key == "independent_support_count" else mentions
            )
            totals[thread_id] += value
            intensity = (
                0 if max_value == 0 else min(4, math.ceil(4 * value / max_value))
            )
            row_cells.append(
                f'<td class="irx-visual__heat-{intensity}"><strong>{value_label}: {value}.</strong> '
                f"Упоминания: {mentions}; независимая поддержка: {independent}.</td>"
            )
        body_rows.append(
            f'<tr><th scope="row">{_e(source["label"])}</th>{"".join(row_cells)}</tr>'
        )
    ranked = sorted(
        threads,
        key=lambda thread: (
            -totals[str(thread["canonical_thread_id"])],
            str(thread["title_ru"]).casefold(),
            str(thread["canonical_thread_id"]),
        ),
    )
    ranked_rows = "".join(
        f"<li><strong>{_e(thread['title_ru'])}</strong>: "
        f"{totals[str(thread['canonical_thread_id'])]} по выбранной метрике.</li>"
        for thread in ranked
    )
    return (
        f"<p>Интенсивность ячейки кодирует {value_label}. Ноль означает классифицированное "
        "отсутствие вклада; «неизвестно» означает недоступную классификацию.</p>"
        '<div class="irx-visual__table-wrap" tabindex="0" '
        'aria-label="Прокручиваемая матрица источников и тем">'
        '<table class="irx-visual__heatmap">'
        f'<thead><tr><th scope="col">Источник</th>{head}</tr></thead>'
        f"<tbody>{''.join(body_rows)}</tbody></table></div>"
        f'<h3>Сводка по темам</h3><ol class="irx-visual__list">{ranked_rows}</ol>',
        False,
        (),
    )


_MATURITY_LEVEL_ORDER = (
    "single_source",
    "repeated_signal",
    "multi_channel",
    "primary_verified",
    "externally_corroborated",
    "decision_grade",
    "unknown",
)
_MATURITY_DISTRIBUTION_LABELS = {
    "single_source": "Один источник",
    "repeated_signal": "Повторяющийся сигнал",
    "multi_channel": "Несколько независимых каналов",
    "primary_verified": "Проверено первичным источником",
    "externally_corroborated": "Подтверждено внешними данными",
    "decision_grade": "Достаточно для решения",
    "unknown": "Зрелость неизвестна",
}


def _validate_evidence_maturity(spec: Mapping[str, object]) -> None:
    _validate_common(spec, {"levels", "thread_count"})
    levels = _expect_list(spec["levels"], "levels", maximum=7)
    thread_count = _expect_int(spec["thread_count"], "thread_count")
    _require_collection_state(spec, levels, "levels")
    if spec["data_status"] in {"empty", "unavailable"} and thread_count != 0:
        _fail(
            "thread_count", "empty/unavailable требует population=0 без maturity zeros"
        )
    total = 0
    for index, raw_level in enumerate(levels):
        path = f"levels[{index}]"
        level = _expect_mapping(raw_level, path)
        _expect_exact_fields(level, required={"key", "label_ru", "count"}, path=path)
        expected = _MATURITY_LEVEL_ORDER[index]
        key = _expect_enum(level["key"], set(_MATURITY_LEVEL_ORDER), f"{path}.key")
        if key != expected:
            _fail(f"{path}.key", f"ожидался уровень {expected}")
        label = _expect_str(
            level["label_ru"], f"{path}.label_ru", russian=True, max_length=180
        )
        if label != _MATURITY_DISTRIBUTION_LABELS[key]:
            _fail(
                f"{path}.label_ru",
                f"ожидалась фиксированная подпись {_MATURITY_DISTRIBUTION_LABELS[key]}",
            )
        total += _expect_int(level["count"], f"{path}.count")
    if levels and len(levels) != len(_MATURITY_LEVEL_ORDER):
        _fail("levels", "available maturity требует все шесть уровней и unknown bucket")
    if total != thread_count:
        _fail("levels", "сумма counts должна точно совпадать с thread_count")
    if spec["data_status"] in {"available", "stale"} and thread_count == 0:
        _fail("thread_count", "нулевая population должна быть data_status=empty")


def _render_evidence_maturity(
    spec: Mapping[str, object],
) -> tuple[str, bool, tuple[str, ...]]:
    if spec["data_status"] in {"empty", "unavailable"}:
        return (
            f"<p>{_e(_state_message('evidence_maturity', str(spec['data_status'])))}</p>",
            False,
            (),
        )
    count = int(spec["thread_count"])
    rows: list[str] = []
    for level in spec["levels"]:
        level_count = int(level["count"])
        percent = 100 * level_count / count
        label = _MATURITY_DISTRIBUTION_LABELS[str(level["key"])]
        rows.append(
            '<div class="irx-visual__bar-row">'
            f"<span>{_e(label)}</span>"
            f'<div class="irx-visual__bar-track" role="img" '
            f'aria-label="{_e(label)}: {level_count} из {count}, {_fmt(percent)} процента">'
            f'<div class="irx-visual__bar" style="width:{_fmt(percent)}%"></div></div>'
            f"<strong>{level_count} ({_fmt(percent)}%)</strong></div>"
        )
    return (
        f"<p>Распределение {count} канонических тем. Все полосы начинаются с нулевой базы; "
        "«Зрелость неизвестна» — отдельная неклассифицированная группа.</p>"
        f"{''.join(rows)}",
        False,
        (),
    )


_LEARNING_STAGE_KEYS = (
    "marked",
    "read",
    "understood",
    "explained",
    "tried",
    "implemented",
    "measured",
)
_LEARNING_STAGE_LABELS = {
    "marked": "Отмечено",
    "read": "Прочитано",
    "understood": "Понято",
    "explained": "Объяснено",
    "tried": "Испробовано",
    "implemented": "Внедрено",
    "measured": "Измерено",
}
_LEARNING_CONFIRMATION_KIND = {
    "marked": "reaction",
    "read": "read_receipt",
    "understood": "comprehension_check",
    "explained": "explanation",
    "tried": "trial",
    "implemented": "implementation",
    "measured": "measurement",
}
_LEARNING_CONFIRMATION_LABEL = {
    "reaction": "личная реакция",
    "read_receipt": "подтверждение чтения",
    "comprehension_check": "проверка понимания",
    "explanation": "подтвержденное объяснение",
    "trial": "подтвержденная проба",
    "implementation": "подтвержденное внедрение",
    "measurement": "подтвержденное измерение",
    "none": "подтверждение отсутствует",
}


def _validate_learning_progression(spec: Mapping[str, object]) -> None:
    _validate_common(spec, {"stages"})
    stages = _expect_list(spec["stages"], "stages", maximum=7)
    _require_collection_state(spec, stages, "stages")
    prior_count: int | None = None
    for index, raw_stage in enumerate(stages):
        path = f"stages[{index}]"
        stage = _expect_mapping(raw_stage, path)
        _expect_exact_fields(
            stage,
            required={
                "key",
                "label_ru",
                "count",
                "observation_status",
                "confirmation_kind",
                "evidence_refs",
            },
            path=path,
        )
        expected_key = _LEARNING_STAGE_KEYS[index]
        key = _expect_enum(stage["key"], set(_LEARNING_STAGE_KEYS), f"{path}.key")
        if key != expected_key:
            _fail(f"{path}.key", f"ожидалась стадия {expected_key}")
        label = _expect_str(
            stage["label_ru"], f"{path}.label_ru", russian=True, max_length=120
        )
        if label != _LEARNING_STAGE_LABELS[key]:
            _fail(
                f"{path}.label_ru",
                f"ожидалась фиксированная подпись {_LEARNING_STAGE_LABELS[key]}",
            )
        observation = _expect_enum(
            stage["observation_status"],
            {"confirmed", "unknown"},
            f"{path}.observation_status",
        )
        kind = _expect_enum(
            stage["confirmation_kind"],
            set(_LEARNING_CONFIRMATION_LABEL),
            f"{path}.confirmation_kind",
        )
        refs = _expect_list(stage["evidence_refs"], f"{path}.evidence_refs", maximum=30)
        validated_refs = [
            _validate_reference(ref, f"{path}.evidence_refs[{ref_index}]")
            for ref_index, ref in enumerate(refs)
        ]
        if len(validated_refs) != len(set(validated_refs)):
            _fail(f"{path}.evidence_refs", "повторяющиеся refs запрещены")
        if observation == "unknown":
            if stage["count"] is not None or kind != "none" or refs:
                _fail(path, "unknown stage требует count=null, kind=none и пустые refs")
            continue
        count = _expect_int(stage["count"], f"{path}.count")
        expected_kind = _LEARNING_CONFIRMATION_KIND[key]
        if kind != expected_kind:
            _fail(
                f"{path}.confirmation_kind",
                f"стадия {key} требует независимое подтверждение {expected_kind}",
            )
        if not refs:
            _fail(f"{path}.evidence_refs", "confirmed stage требует evidence refs")
        if prior_count is not None and count > prior_count:
            _fail(f"{path}.count", "learning progression должна быть невозрастающей")
        prior_count = count
    if stages and len(stages) != len(_LEARNING_STAGE_KEYS):
        _fail("stages", "available progression требует все семь стадий")
    confirmed_counts = [
        int(stage["count"])
        for stage in stages
        if stage["observation_status"] == "confirmed"
    ]
    if stages and confirmed_counts and max(confirmed_counts) == 0:
        _fail("stages", "нулевой подтвержденный прогресс должен быть data_status=empty")
    if stages and any(stage["observation_status"] == "unknown" for stage in stages):
        if not spec.get("partial_reasons_ru"):
            _fail("partial_reasons_ru", "unknown stage требует явную partial-причину")


def _render_learning_progression(
    spec: Mapping[str, object],
) -> tuple[str, bool, tuple[str, ...]]:
    if spec["data_status"] in {"empty", "unavailable"}:
        return (
            f"<p>{_e(_state_message('learning_progression', str(spec['data_status'])))}</p>",
            False,
            (),
        )
    rows: list[str] = []
    for stage in spec["stages"]:
        label = _LEARNING_STAGE_LABELS[str(stage["key"])]
        if stage["observation_status"] == "unknown":
            rows.append(
                f'<li class="irx-visual__unknown"><strong>{_e(label)}</strong>: '
                "неизвестно; подтвержденное событие отсутствует.</li>"
            )
        else:
            rows.append(
                f"<li><strong>{_e(label)}</strong>: подтвержденных событий — "
                f"{_e(stage['count'])}; "
                f"основание — {_e(_LEARNING_CONFIRMATION_LABEL[str(stage['confirmation_kind'])])}.</li>"
            )
    return (
        "<p>Каждая стадия имеет собственное наблюдаемое основание. Личная реакция подтверждает "
        "только стадию «Отмечено» и не доказывает чтение или понимание.</p>"
        f'<ol class="irx-visual__flow">{"".join(rows)}</ol>',
        False,
        (),
    )


def _validate_evidence_badge(spec: Mapping[str, object]) -> None:
    fields = {
        "confidence",
        "confidence_reason_ru",
        "evidence_maturity",
        "source_count",
        "independent_source_count",
    }
    _validate_common(spec, fields)
    status = str(spec["data_status"])
    values = (
        spec["confidence"],
        spec["confidence_reason_ru"],
        spec["evidence_maturity"],
        spec["source_count"],
        spec["independent_source_count"],
    )
    if status in {"empty", "unavailable"}:
        if any(value is not None for value in values):
            _fail("spec", f"{status} badge требует null вместо вымышленных значений")
        return
    _expect_enum(spec["confidence"], _CONFIDENCE, "confidence")
    _expect_str(
        spec["confidence_reason_ru"],
        "confidence_reason_ru",
        russian=True,
        max_length=500,
    )
    _expect_enum(spec["evidence_maturity"], _MATURITY, "evidence_maturity")
    source_count = _expect_int(spec["source_count"], "source_count")
    independent = _expect_int(
        spec["independent_source_count"], "independent_source_count"
    )
    if independent > source_count:
        _fail("independent_source_count", "не может превышать source_count")
    if source_count == 0:
        _fail("source_count", "available/stale badge требует хотя бы один источник")
    if (
        spec["evidence_maturity"] in {"multi_channel", "externally_corroborated"}
        and independent < 2
    ):
        _fail(
            "independent_source_count",
            "multi-channel/external maturity требует минимум два независимых источника",
        )


def _render_evidence_badge(
    spec: Mapping[str, object],
) -> tuple[str, bool, tuple[str, ...]]:
    if spec["data_status"] in {"empty", "unavailable"}:
        return (
            f"<p>{_e(_state_message('evidence_badge', str(spec['data_status'])))}</p>",
            False,
            (),
        )
    return (
        "<p>Поддерживающая маркировка: она поясняет утверждение, но не считается отдельной "
        'содержательной визуализацией.</p><div class="irx-visual__badge-pair">'
        '<div class="irx-visual__badge"><strong>Уверенность</strong><br>'
        f"{_e(_CONFIDENCE_LABELS[str(spec['confidence'])])}. "
        f"{_e(spec['confidence_reason_ru'])}</div>"
        '<div class="irx-visual__badge irx-visual__badge--maturity">'
        "<strong>Зрелость доказательств</strong><br>"
        f"{_e(_MATURITY_LABELS[str(spec['evidence_maturity'])])}. "
        f"Источников: {_e(spec['source_count'])}; независимых: "
        f"{_e(spec['independent_source_count'])}.</div></div>",
        False,
        (),
    )


_VALIDATORS: dict[str, Callable[[Mapping[str, object]], None]] = {
    "decision_matrix": _validate_decision_matrix,
    "reaction_funnel": _validate_reaction_funnel,
    "radar_gate": _validate_radar_gate,
    "project_impact": _validate_project_impact,
    "knowledge_graph": _validate_knowledge_graph,
    "thread_timeline": _validate_thread_timeline,
    "source_thread_heatmap": _validate_source_thread_heatmap,
    "evidence_maturity": _validate_evidence_maturity,
    "learning_progression": _validate_learning_progression,
    "evidence_badge": _validate_evidence_badge,
}
_RENDERERS: dict[
    str, Callable[[Mapping[str, object]], tuple[str, bool, tuple[str, ...]]]
] = {
    "decision_matrix": _render_decision_matrix,
    "reaction_funnel": _render_reaction_funnel,
    "radar_gate": _render_radar_gate,
    "project_impact": _render_project_impact,
    "knowledge_graph": _render_knowledge_graph,
    "thread_timeline": _render_thread_timeline,
    "source_thread_heatmap": _render_source_thread_heatmap,
    "evidence_maturity": _render_evidence_maturity,
    "learning_progression": _render_learning_progression,
    "evidence_badge": _render_evidence_badge,
}


def validate_report_visual(spec: Mapping[str, object]) -> str:
    """Validate one component spec and return its stable component type.

    This strict entry point is useful to producers.  Reader renderers should use
    :func:`render_report_visual`, which turns a validation failure into an
    accessible, nonblank failed component.
    """

    if not isinstance(spec, Mapping):
        _fail("spec", "ожидался объект")
    schema = spec.get("schema_version")
    if not isinstance(schema, str) or schema not in _SCHEMA_TO_COMPONENT:
        _fail("schema_version", "неподдерживаемая версия schema")
    component_type = _SCHEMA_TO_COMPONENT[schema]
    _VALIDATORS[component_type](spec)
    return component_type


def _safe_failed_identity(spec: object) -> tuple[str, str, str, str]:
    if not isinstance(spec, Mapping):
        return "invalid-visual", "invalid", "report_visual.invalid.v1", "unavailable"
    schema_raw = spec.get("schema_version")
    schema = (
        schema_raw
        if isinstance(schema_raw, str) and len(schema_raw) <= 80
        else "report_visual.invalid.v1"
    )
    component_type = _SCHEMA_TO_COMPONENT.get(schema, "invalid")
    component_raw = spec.get("component_id")
    component_id = (
        component_raw
        if isinstance(component_raw, str) and _COMPONENT_ID_RE.fullmatch(component_raw)
        else "invalid-visual"
    )
    data_raw = spec.get("data_status")
    data_status = (
        data_raw
        if isinstance(data_raw, str) and data_raw in _DATA_STATUSES
        else "unavailable"
    )
    return component_id, component_type, schema, data_status


def _failed_html(
    component_id: str,
    component_type: str,
    schema_version: str,
    data_status: str,
    warning: str,
) -> str:
    heading_id = f"{component_id}-title"
    return (
        '<section class="irx-visual irx-visual--failed" data-irx-visual="true" '
        f'data-component="{_e(component_type)}" data-component-id="{_e(component_id)}" '
        f'data-schema-version="{_e(schema_version)}" data-render-status="failed" '
        f'data-data-status="{_e(data_status)}" data-source-ref-count="0" '
        f'data-visual-role="invalid" aria-labelledby="{_e(heading_id)}">'
        f'<h2 class="irx-visual__heading" id="{_e(heading_id)}">Визуализация не построена</h2>'
        '<div class="irx-visual__state irx-visual__state--failed" role="alert">'
        f"<strong>Ошибка схемы.</strong> {_e(warning)}</div>"
        '<p class="irx-visual__note">Исправьте структурированный вход; компонент не был '
        "заменен пустым SVG или предполагаемыми значениями.</p></section>"
    )


def render_report_visual(spec: Mapping[str, object]) -> ReportVisualResult:
    """Validate and deterministically render one Report V2 component."""

    try:
        component_type = validate_report_visual(spec)
    except ReportVisualValidationError as exc:
        component_id, component_type, schema, data_status = _safe_failed_identity(spec)
        warning = str(exc)
        return ReportVisualResult(
            html=_failed_html(
                component_id, component_type, schema, data_status, warning
            ),
            component_id=component_id,
            component_type=component_type,
            schema_version=schema,
            render_status="failed",
            data_status=data_status,
            source_ref_count=0,
            warnings=(warning,),
        )

    body, extra_partial, extra_warnings = _RENDERERS[component_type](spec)
    source_ref_count = len(spec["source_refs"])
    render_status = _render_status(spec, extra_partial=extra_partial)
    warnings = _result_warnings(
        spec,
        *extra_warnings,
        extra_partial=extra_partial,
    )
    return ReportVisualResult(
        html=_section(
            spec,
            component_type,
            body,
            render_status=render_status,
            source_ref_count=source_ref_count,
        ),
        component_id=str(spec["component_id"]),
        component_type=component_type,
        schema_version=str(spec["schema_version"]),
        render_status=render_status,
        data_status=str(spec["data_status"]),
        source_ref_count=source_ref_count,
        warnings=warnings,
    )


def render_visual_document(
    specs: Sequence[Mapping[str, object]],
    *,
    title_ru: str = "Компоненты отчета V2",
) -> str:
    """Compose a neutral, standalone, offline gallery for fixtures/consumers."""

    title = _expect_str(title_ru, "title_ru", russian=True, max_length=160)
    initial_results = [render_report_visual(spec) for spec in specs]
    fallback_positions = {
        position
        for position, spec in enumerate(specs)
        if not isinstance(spec, Mapping)
        or not isinstance(spec.get("component_id"), str)
        or not _COMPONENT_ID_RE.fullmatch(spec["component_id"])
    }
    reserved_document_ids: set[str] = set()
    for position, result in enumerate(initial_results):
        if position not in fallback_positions:
            reserved_document_ids.add(result.component_id)
            reserved_document_ids.update(re.findall(r'\sid="([^"]+)"', result.html))

    rendered: list[ReportVisualResult] = []
    for position, result in enumerate(initial_results, start=1):
        if position - 1 in fallback_positions:
            base_component_id = f"invalid-visual-{position}"
            component_id = base_component_id
            collision_index = 2
            while (
                component_id in reserved_document_ids
                or f"{component_id}-title" in reserved_document_ids
            ):
                component_id = f"{base_component_id}-{collision_index}"
                collision_index += 1
            reserved_document_ids.update({component_id, f"{component_id}-title"})
            warning = (
                result.warnings[0] if result.warnings else "неизвестная ошибка схемы"
            )
            result = ReportVisualResult(
                html=_failed_html(
                    component_id,
                    result.component_type,
                    result.schema_version,
                    result.data_status,
                    warning,
                ),
                component_id=component_id,
                component_type=result.component_type,
                schema_version=result.schema_version,
                render_status=result.render_status,
                data_status=result.data_status,
                source_ref_count=result.source_ref_count,
                warnings=result.warnings,
            )
        rendered.append(result)
    ids = [result.component_id for result in rendered]
    if len(ids) != len(set(ids)):
        raise ReportVisualValidationError(
            "component_id: повторяющиеся DOM id запрещены в одном документе"
        )
    valid_specs = [
        spec
        for spec, result in zip(specs, rendered)
        if result.render_status != "failed"
    ]
    identity_fields = (
        "run_id",
        "reporting_week",
        "analysis_period_start",
        "analysis_period_end",
    )
    if valid_specs:
        expected_identity = tuple(valid_specs[0][field] for field in identity_fields)
        for index, spec in enumerate(valid_specs[1:], start=1):
            identity = tuple(spec[field] for field in identity_fields)
            if identity != expected_identity:
                raise ReportVisualValidationError(
                    "document identity: все валидные компоненты должны иметь один "
                    f"run_id/reporting_week/analysis_period; mismatch at valid spec {index}"
                )
    rendered_html = "".join(result.html for result in rendered)
    document_ids = re.findall(r'\sid="([^"]+)"', rendered_html)
    duplicate_dom_ids = sorted(
        {value for value in document_ids if document_ids.count(value) > 1}
    )
    if duplicate_dom_ids:
        raise ReportVisualValidationError(
            "DOM id: производные id компонентов конфликтуют: "
            + ", ".join(duplicate_dom_ids)
        )
    csp = (
        "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
        "font-src 'none'; script-src 'none'; connect-src 'none'; object-src 'none'; "
        "base-uri 'none'; form-action 'none'"
    )
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta http-equiv="Content-Security-Policy" content="{_e(csp)}">'
        f"<title>{_e(title)}</title><style>{REPORT_VISUALS_CSS}</style></head>"
        f'<body><main class="irx-report"><h1 class="irx-report__title">{_e(title)}</h1>'
        f"{rendered_html}</main></body></html>"
    )


__all__ = [
    "REPORT_VISUALS_CONTRACT_VERSION",
    "REPORT_VISUALS_CSS",
    "SUPPORTED_VISUAL_SCHEMAS",
    "ReportVisualResult",
    "ReportVisualValidationError",
    "render_report_visual",
    "render_visual_document",
    "report_visual_styles",
    "validate_report_visual",
]
