# PA-14 — inspectable memory and knowledge library (local evidence)

Date: 2026-09-24
Boundary: local, explicit-path SQLite sidecar only. No default database,
network, provider egress, scheduler or hidden profile learning.

## Implemented

`src/prm/memory_library.py`:

- `MemoryItem` with an explicit `state` (`active|forgotten`) and a separate
  `engagement` axis (`none|indexed|opened|read|applied`) so indexing, opening,
  reading and applying are never conflated; source ref, digest, version and
  timestamps stay visible.
- `MemoryLibraryStore` (explicit path): save/get/list, `item_history`,
  `set_engagement`, `revise_item` (new version, prior versions retained),
  `forget_item`, and bounded `export_items`.
- `plan_forget` / `DerivedPropagationPlan`: forgetting returns an explicit
  cleanup plan for derived `index`, `cache` and `jobs`; unrelated archive items
  are untouched.
- Explicit preferences (`interest|project|depth|length|source|topic`).
  Feedback **never** mutates memory by itself: `propose_preference` records a
  proposal and `confirm_preference` applies it once, after which
  `deactivate_preference` reverses it while `history_preferences` keeps every
  revision.
- `require_memory_access`: fail-closed PA-02 check for the `memory.manage`
  purpose (read/write/delete) on the local provider.

## Verification

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_memory.py
# 6 passed

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 555 passed
```

The suite is registered in `focused-prm` (and therefore `fast-contract`).

## Remaining gates

Runtime verification remains: wiring the store to the live assistant, actual
propagation of a forget across real derived indexes/caches/jobs, and operator
use of preferences to change selection quality. This slice is the local,
inspectable contract; it makes no hidden-learning or acceptance claim.
