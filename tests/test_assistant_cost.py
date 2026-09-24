from datetime import datetime, timezone

import pytest

from prm.model_cost import (
    CacheEntry,
    ModelCatalogEntry,
    QualityComparison,
    RouteRequest,
    Tariff,
    UsageRecord,
    cost_per_success,
    estimate_cost,
    is_cacheable,
    savings_claim,
    select_route,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _entry(model_id, *, quality=3, privacy="zero_retention", tariff=True, context=200000, cache=False):
    return ModelCatalogEntry(
        model_id=model_id,
        provider_ref="provider_openai",
        quality_tier=quality,
        privacy_class=privacy,  # type: ignore[arg-type]
        stability="stable",
        context_limit=context,
        tariff=Tariff(version="2026-09", input_per_mtok=1.0, output_per_mtok=2.0) if tariff else None,
        supports_cache=cache,
    )


def _request(**changes):
    values = {
        "task_type": "brief.editorial",
        "required_quality": 3,
        "privacy_required": True,
        "context_tokens": 10000,
        "expected_output_tokens": 2000,
    }
    values.update(changes)
    return RouteRequest(**values)  # type: ignore[arg-type]


def test_select_route_is_quality_first_and_privacy_safe():
    catalog = (_entry("model_mid", quality=3), _entry("model_strong", quality=5))
    entry, status = select_route(catalog, _request())
    assert status == "ok"
    assert entry.model_id == "model_strong"  # quality beats cheap
    # Privacy-required excludes a standard-retention model.
    catalog = (_entry("model_standard", quality=5, privacy="standard"), _entry("model_zdr", quality=3))
    entry, status = select_route(catalog, _request(required_quality=3))
    assert entry.model_id == "model_zdr"


def test_unknown_pricing_and_context_are_ineligible():
    catalog = (_entry("model_unknown_price", tariff=False),)
    entry, status = select_route(catalog, _request())
    assert entry is None and status == "no_eligible_route"
    catalog = (_entry("model_small", context=1000),)
    entry, status = select_route(catalog, _request(context_tokens=5000, expected_output_tokens=2000))
    assert entry is None and status == "no_eligible_route"


def test_quality_below_required_is_not_silently_downgraded():
    catalog = (_entry("model_weak", quality=2),)
    entry, status = select_route(catalog, _request(required_quality=4))
    assert entry is None and status == "quality_below_required"
    entry, status = select_route(catalog, _request(required_quality=4, allow_fallback=True))
    assert entry is not None and status == "quality_fallback"


def test_estimate_cost_unknown_is_none_never_zero():
    entry = _entry("model_mid")
    usage = UsageRecord(
        task_type="brief.editorial", requested_model="model_mid", observed_model="model_mid",
        tariff_version="2026-09", input_tokens=1000, output_tokens=500, cached_tokens=0, reasoning_tokens=0,
        latency_ms=1200, retries=0, succeeded=True, estimated_cost_usd=0.0, recorded_at=NOW,
    )
    assert estimate_cost(entry, usage) == pytest.approx((1000 * 1.0 + 500 * 2.0) / 1_000_000)
    assert estimate_cost(_entry("model_unknown_price", tariff=False), usage) is None


def test_cost_per_success_counts_failures_and_unknown_pricing():
    def record(success, cost, model="model_mid"):
        return UsageRecord(
            task_type="brief.editorial", requested_model=model, observed_model=model, tariff_version="2026-09",
            input_tokens=1000, output_tokens=500, cached_tokens=0, reasoning_tokens=0, latency_ms=1000,
            retries=1, succeeded=success, estimated_cost_usd=cost, recorded_at=NOW,
        )

    records = (record(True, 0.10), record(True, 0.10), record(False, 0.05))
    assert cost_per_success(records) == pytest.approx(0.125)
    assert cost_per_success((record(False, 0.05),)) is None  # no success
    assert cost_per_success((record(True, None),)) is None  # unknown pricing


def test_savings_require_matched_quality():
    good = QualityComparison(4.0, 4.0, 4.0, 4.0)
    assert savings_claim(good, cost_before=1.0, cost_after=0.6)["claim"] == "saving"
    worse_editorial = QualityComparison(4.0, 4.0, 3.0, 4.0)
    assert savings_claim(worse_editorial, cost_before=1.0, cost_after=0.6)["claim"] == "none"
    not_cheaper = QualityComparison(4.0, 4.0, 4.0, 4.0)
    assert savings_claim(not_cheaper, cost_before=1.0, cost_after=1.0)["claim"] == "none"


def test_usage_record_is_metadata_only():
    fields = set(UsageRecord.__dataclass_fields__)
    assert not ({"text", "content", "prompt", "answer", "body"} & fields)
    with pytest.raises(ValueError):
        UsageRecord(
            task_type="brief.editorial", requested_model="m", observed_model="m", tariff_version="t",
            input_tokens=-1, output_tokens=0, cached_tokens=0, reasoning_tokens=0, latency_ms=0,
            retries=0, succeeded=True, estimated_cost_usd=0.0, recorded_at=NOW,
        )


def test_cacheable_requires_capable_model_and_deterministic_task():
    assert is_cacheable(_entry("model_cache", cache=True), deterministic=True) is True
    assert is_cacheable(_entry("model_cache", cache=True), deterministic=False) is False
    assert is_cacheable(_entry("model_nocache"), deterministic=True) is False
    with pytest.raises(ValueError):
        CacheEntry(key="bad", task_type="brief.editorial", input_digest="a" * 64, created_at=NOW, expires_at=NOW)
