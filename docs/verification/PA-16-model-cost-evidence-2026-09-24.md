# PA-16 — measured model and cost architecture (local evidence)

Date: 2026-09-24
Boundary: local computation only. No network, provider call, database,
credential or live account. No private text is stored or measured.

## Implemented

`src/prm/model_cost.py`:

- `Tariff` (exact version + per-1M-token input/output/cached/reasoning prices)
  and `ModelCatalogEntry` (quality tier, privacy class, stability, context
  limit, tariff, cache support). A `None` tariff means unknown pricing.
- `select_route` is quality-first: it only considers routes whose tariff is
  known, whose context fits, and whose retention satisfies the request. A
  privacy requirement is never silently relaxed, and a quality shortfall is
  reported (`quality_below_required`) unless an explicit `allow_fallback`
  returns `quality_fallback`.
- `estimate_cost` returns `None` for unknown pricing — unknown is never treated
  as zero, so spend is never underestimated. `cost_per_success` sums all spend
  (including failures) over successful complete tasks, and returns `None` when
  any price is unknown or no task succeeded.
- `UsageRecord` is metadata only: requested/observed model, tariff version,
  token classes, latency, retries, success and estimated cost. There is no
  field for private text.
- `QualityComparison` + `savings_claim`: a saving is claimed only with matched
  or better editorial **and** multi-turn usefulness; otherwise the claim is
  `none`.
- `is_cacheable` requires both a cache-capable model and a deterministic task.

## Verification

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_cost.py
# 8 passed

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 569 passed
```

The suite is registered in `focused-prm` (and therefore `fast-contract`).

## Remaining gates

Runtime verification remains: real matched-quality measurements on complete
tasks, live tariff verification against providers, and cache hit-rate evidence.
No token-saving percentage is asserted by this slice.
