"""PA-16 local, fail-closed model routing and cost accounting.

Quality-first selection with a privacy-compatible fallback. Unknown pricing is
never treated as zero and never silently broadens permissions or downgrades
privacy; a route is ineligible when its tariff is unknown or its retention does
not satisfy the request. Usage records carry only metadata — model, tariff,
token classes, latency, retries and cost — never private text. Any claimed
saving requires matched editorial and multi-turn quality evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import re
from typing import Literal, Mapping, Sequence


COST_SCHEMA_VERSION = "assistant.model_cost.v1"
PRIVACY_CLASSES = ("zero_retention", "standard")
STABILITY = ("stable", "preview")
TOKEN_CLASSES = ("input", "output", "cached", "reasoning")

_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,511}$")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class Tariff:
    """Per-1M-token prices for one exact tariff version."""

    version: str
    input_per_mtok: float
    output_per_mtok: float
    # None means the price for this token class is unknown, so any non-zero
    # usage of it must not be priced at zero.
    cached_per_mtok: float | None = None
    reasoning_per_mtok: float | None = None

    def __post_init__(self) -> None:
        _REF_full = re.fullmatch(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,191}$", self.version)
        if not _REF_full:
            raise ValueError("invalid tariff version")
        for name, value in (
            ("input_per_mtok", self.input_per_mtok),
            ("output_per_mtok", self.output_per_mtok),
            ("cached_per_mtok", self.cached_per_mtok),
            ("reasoning_per_mtok", self.reasoning_per_mtok),
        ):
            if value is None:
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative number or None")


@dataclass(frozen=True, slots=True)
class ModelCatalogEntry:
    model_id: str
    provider_ref: str
    quality_tier: int  # 1..5, higher is stronger
    privacy_class: Literal["zero_retention", "standard"]
    stability: Literal["stable", "preview"]
    context_limit: int
    tariff: Tariff | None = None  # None means unknown pricing
    supports_cache: bool = False

    def __post_init__(self) -> None:
        _REF_ok = re.fullmatch(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,191}$", self.model_id)
        if not _REF_ok or not _REF.fullmatch(self.provider_ref):
            raise ValueError("invalid model identity")
        if not isinstance(self.quality_tier, int) or isinstance(self.quality_tier, bool) or not 1 <= self.quality_tier <= 5:
            raise ValueError("quality_tier is out of range")
        if self.privacy_class not in PRIVACY_CLASSES:
            raise ValueError("invalid privacy class")
        if self.stability not in STABILITY:
            raise ValueError("invalid stability")
        if not isinstance(self.context_limit, int) or isinstance(self.context_limit, bool) or self.context_limit < 1000:
            raise ValueError("context_limit is out of range")
        if self.tariff is not None and type(self.tariff) is not Tariff:
            raise ValueError("tariff must be a Tariff or None")


@dataclass(frozen=True, slots=True)
class RouteRequest:
    task_type: str
    required_quality: int
    privacy_required: bool
    context_tokens: int
    expected_output_tokens: int
    allow_fallback: bool = False

    def __post_init__(self) -> None:
        _REF_ok = re.fullmatch(r"^[a-z][a-z0-9_.:-]{2,63}$", self.task_type)
        if not _REF_ok:
            raise ValueError("invalid task_type")
        if not isinstance(self.required_quality, int) or isinstance(self.required_quality, bool) or not 1 <= self.required_quality <= 5:
            raise ValueError("required_quality is out of range")
        if not isinstance(self.context_tokens, int) or isinstance(self.context_tokens, bool) or self.context_tokens < 0:
            raise ValueError("context_tokens is out of range")
        if not isinstance(self.expected_output_tokens, int) or isinstance(self.expected_output_tokens, bool) or self.expected_output_tokens < 0:
            raise ValueError("expected_output_tokens is out of range")


def _privacy_ok(entry: ModelCatalogEntry, request: RouteRequest) -> bool:
    return (not request.privacy_required) or entry.privacy_class == "zero_retention"


def select_route(
    catalog: Sequence[ModelCatalogEntry],
    request: RouteRequest,
) -> tuple[ModelCatalogEntry | None, str]:
    """Quality-first eligible route; a downgrade is explicit, never silent."""

    eligible = [
        entry
        for entry in catalog
        if _privacy_ok(entry, request)
        and entry.tariff is not None
        and entry.context_limit >= request.context_tokens + request.expected_output_tokens
    ]
    if not eligible:
        return None, "no_eligible_route"
    top_quality = max(entry.quality_tier for entry in eligible)
    if top_quality < request.required_quality:
        if not request.allow_fallback:
            return None, "quality_below_required"
        # Fallback keeps the best available quality; the caller must surface it.
        best = max(eligible, key=lambda entry: (entry.quality_tier, -_estimate(entry, request)))
        return best, "quality_fallback"
    best = min(
        (entry for entry in eligible if entry.quality_tier >= request.required_quality),
        key=lambda entry: (-entry.quality_tier, _estimate(entry, request)),
    )
    return best, "ok"


def _estimate(entry: ModelCatalogEntry, request: RouteRequest) -> float:
    assert entry.tariff is not None
    return (
        request.context_tokens * entry.tariff.input_per_mtok
        + request.expected_output_tokens * entry.tariff.output_per_mtok
    ) / 1_000_000


def estimate_cost(entry: ModelCatalogEntry, usage: "UsageRecord") -> float | None:
    """Return None when pricing is unknown; never treat unknown as zero."""

    if entry.tariff is None:
        return None
    tariff = entry.tariff
    # Unknown price for a token class that was actually used => unknown total.
    if usage.cached_tokens > 0 and tariff.cached_per_mtok is None:
        return None
    if usage.reasoning_tokens > 0 and tariff.reasoning_per_mtok is None:
        return None
    return (
        usage.input_tokens * tariff.input_per_mtok
        + usage.output_tokens * tariff.output_per_mtok
        + usage.cached_tokens * (tariff.cached_per_mtok or 0.0)
        + usage.reasoning_tokens * (tariff.reasoning_per_mtok or 0.0)
    ) / 1_000_000


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """Metadata only; there is deliberately no field for private text."""

    task_type: str
    requested_model: str
    observed_model: str
    tariff_version: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    reasoning_tokens: int
    latency_ms: int
    retries: int
    succeeded: bool
    estimated_cost_usd: float | None
    recorded_at: datetime
    schema_version: str = COST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != COST_SCHEMA_VERSION:
            raise ValueError("unsupported cost schema version")
        if not re.fullmatch(r"^[a-z][a-z0-9_.:-]{2,63}$", self.task_type):
            raise ValueError("invalid task_type")
        for name, value in (("requested_model", self.requested_model), ("observed_model", self.observed_model), ("tariff_version", self.tariff_version)):
            if not re.fullmatch(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,191}$", value):
                raise ValueError(f"invalid {name}")
        for name, value in (
            ("input_tokens", self.input_tokens), ("output_tokens", self.output_tokens),
            ("cached_tokens", self.cached_tokens), ("reasoning_tokens", self.reasoning_tokens),
            ("latency_ms", self.latency_ms), ("retries", self.retries),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.estimated_cost_usd is not None and (
            not isinstance(self.estimated_cost_usd, (int, float))
            or isinstance(self.estimated_cost_usd, bool)
            or self.estimated_cost_usd < 0
        ):
            raise ValueError("estimated_cost_usd must be non-negative or None")
        _utc(self.recorded_at)

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "task_type": self.task_type,
            "requested_model": self.requested_model,
            "observed_model": self.observed_model,
            "tariff_version": self.tariff_version,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "latency_ms": self.latency_ms,
            "retries": self.retries,
            "succeeded": self.succeeded,
            "estimated_cost_usd": self.estimated_cost_usd,
            "recorded_at": _utc(self.recorded_at).isoformat().replace("+00:00", "Z"),
        }


def cost_per_success(records: Sequence[UsageRecord]) -> float | None:
    """Total recorded spend over successful complete tasks; None if no success."""

    if any(record.estimated_cost_usd is None for record in records):
        return None
    successes = sum(1 for record in records if record.succeeded)
    if successes == 0:
        return None
    total = sum(float(record.estimated_cost_usd or 0.0) for record in records)
    return round(total / successes, 6)


@dataclass(frozen=True, slots=True)
class QualityComparison:
    """Editorial and multi-turn usefulness are required before any saving claim."""

    baseline_editorial: float
    baseline_multiturn: float
    candidate_editorial: float
    candidate_multiturn: float

    def __post_init__(self) -> None:
        for name, value in (
            ("baseline_editorial", self.baseline_editorial), ("baseline_multiturn", self.baseline_multiturn),
            ("candidate_editorial", self.candidate_editorial), ("candidate_multiturn", self.candidate_multiturn),
        ):
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 5:
                raise ValueError(f"{name} must be between 0 and 5")


def savings_claim(
    comparison: QualityComparison,
    *,
    cost_before: float,
    cost_after: float,
) -> dict[str, object]:
    """A saving is claimed only with matched-or-better quality on both axes."""

    quality_ok = (
        comparison.candidate_editorial >= comparison.baseline_editorial
        and comparison.candidate_multiturn >= comparison.baseline_multiturn
    )
    if cost_before < 0 or cost_after < 0:
        raise ValueError("costs must be non-negative")
    cheaper = cost_after < cost_before
    if not quality_ok or not cheaper:
        return {"claim": "none", "quality_matched": quality_ok, "reason": "quality_not_matched" if not quality_ok else "not_cheaper"}
    saved = round(cost_before - cost_after, 6)
    return {
        "claim": "saving",
        "quality_matched": True,
        "saved_usd": saved,
        "saved_fraction": round(saved / cost_before, 4) if cost_before else None,
    }


@dataclass(frozen=True, slots=True)
class CacheEntry:
    key: str
    task_type: str
    input_digest: str
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if not re.fullmatch(r"^cache_[a-z0-9_-]{3,120}$", self.key):
            raise ValueError("invalid cache key")
        if not re.fullmatch(r"^[a-z][a-z0-9_.:-]{2,63}$", self.task_type):
            raise ValueError("invalid task_type")
        if not re.fullmatch(r"[0-9a-f]{64}", self.input_digest):
            raise ValueError("invalid input digest")
        if _utc(self.expires_at) <= _utc(self.created_at):
            raise ValueError("cache entry must expire after creation")


def is_cacheable(entry: ModelCatalogEntry, *, deterministic: bool) -> bool:
    """Only deterministic tasks on cache-capable models may be cached."""

    return bool(entry.supports_cache and deterministic)
