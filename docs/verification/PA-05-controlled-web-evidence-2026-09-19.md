# PA-05 controlled public-web evidence — 2026-09-19

Status: locally verified, offline fixture evidence only. This does not grant
live provider/credential/account authority, runtime acceptance, release
approval, or formal approval of the mechanically `review_required` PA design.

## Implemented scope

Implementation commit: `7aeb66e` (`feat(pa05): add controlled public web
evidence`) on
`docs/personal-assistant-blueprint-playbook-20260918`.

- A current-fact route may use public search only when it receives a separate
  minimized query, a matching SHA-256 scope digest, a typed PA-02
  `PublicWebAccess`, an injected provider adapter, and fixed bounds. The
  default application supplies no adapter or bounds and fails closed.
- Search and primary-document fetch consume separate public `read`
  reservations. Private/archive classes, fallback providers, raw operator
  query construction, and implicit archive access are absent from this path.
- Only exact caller-scoped HTTPS source hosts may bridge discovery to fetch.
  The fetch transport rejects userinfo, nonstandard ports, IP literals,
  redirects, unsafe DNS results, proxy inheritance, unsupported content,
  oversized bodies, and source instructions. Its checked DNS addresses are
  pinned for the actual TLS TCP dial; hostname remains used for SNI and
  certificate validation.
- Search snippets remain discovery-only. Only fresh fetched primary-source
  spans enter evidence and the final answer renderer; stale, partial,
  conflicting, unavailable, and injected-source outcomes render a current-fact
  boundary with explicit coverage gaps.
- The legacy `src/external_watch/fetch.py` UTD allowlist was not changed.
  No production DB, live job, timer, `.env`, credential, provider account,
  Telegram account, or live network call was used. The two pre-existing
  untracked local files were not staged or changed.

## Focused verification

Environment: Python 3.10.12; `PYTHONPATH=src` and
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` where shown.

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_web_search.py \
  tests/test_prm_request_plan.py \
  tests/test_assistant_contracts.py \
  tests/test_prm_application.py \
  tests/test_prm_bot_dispatch.py \
  tests/test_primary_source_verification.py \
  tests/test_external_watch_fetch_safety.py
# 70 passed in 6.39s

python3 tools/playbook.py --check-pin
# Playbook pin verified; no model, hook or application runtime enabled.

python3 tools/check_personal_assistant_plan.py
# PA plan: 19 consistent slices; schemas, references, dependencies and context limits passed.
# Design state: review_required; no product, human-approval or runtime claim.

tasktmp=$(mktemp -d)
TMPDIR="$tasktmp" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 363 passed in 83.01s

git diff --check
# passed
```

The PA-05 tests are synthetic adapters and mocked DNS only. They demonstrate
application wiring, scope separation, query-substitution refusal,
primary-source filtering, stale/partial/conflicting coverage, SSRF/redirect
rejection, and prompt-injection exclusion. They do not demonstrate live search
quality, provider configuration, DNS behavior on a real network, certificate
operations, or operator usefulness.

## Review and remaining gates

No new reviewer was launched for this slice: the owner directed that the next
Deep Review be accumulated at the PA-04..PA-06 boundary, and the previous
Astra/high plus Terra/high reviews cover PA-04 rather than this diff. PA-05 is
not claimed human-accepted or formally complete in `docs/tasks.md`.

Before any live adapter configuration or egress, a real credential/provider
and runtime authorization gate remains required. The next planned engineering
slice is PA-06; its phase-boundary Deep Review must include the accumulated
PA-04..PA-06 diff and must not be inferred from fixture tests.
