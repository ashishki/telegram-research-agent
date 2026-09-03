# UTD Live Watch Enablement Receipt — 2026-09-03

Status: timer enabled, delivery fail-closed pending confirmed UTD profile

This receipt records controlled live UTD watch enablement for the existing
`prm-assistant` Telegram bot. It is not a second bot, not a legacy report timer,
not external embeddings/vector adoption, not provider-backed web research, not
an automatic profile mutation, and not a PRM-19 release claim.

## Operator Approval

The operator instructed Codex to proceed end-to-end on 2026-09-03 after the live
source/timer/delivery plan was described. This was treated as approval to enable
the bounded UTD live watch timer and Telegram delivery gate while preserving:

- confirmed-profile gating;
- allowlisted official UTD Calendar / ISSO / Basic Needs sources;
- sidecar shadow/delivery receipts;
- relevance ranking and max-five candidate cap;
- default-deny/killswitch controls;
- no automatic confirmed-profile changes from feedback;
- no autonomous university-system actions.

## Runtime State

- Installed systemd units:
  - `telegram-utd-watch.service`
  - `telegram-utd-watch.timer`
- Timer cadence:
  - `OnBootSec=15m`
  - `OnUnitActiveSec=45m`
  - `RandomizedDelaySec=180`
- Delivery gate:
  - service sets `UTD_WATCH_DELIVERY_ENABLED=1`
  - service sets `UTD_WATCH_KILL_SWITCH=0`
  - command still requires `--enable-delivery`
  - runtime still requires Telegram token/chat id and confirmed unexpired UTD profile
- Sidecar DB:
  - `data/utd_shadow.db`

## Preflight Evidence

Command:

```bash
PYTHONPATH=src python3 -m external_watch.live --enable-shadow --show-candidates
```

Observed sanitized output before enabling delivery:

```json
{
  "shadow_enabled": true,
  "profile_loaded": false,
  "change_count": 0,
  "candidate_count": 0,
  "candidates": [],
  "delivery": {"enabled": false, "sent": 0},
  "source_status": {}
}
```

After installing and manually starting the systemd service:

```json
{
  "shadow_enabled": true,
  "profile_loaded": false,
  "change_count": 0,
  "candidate_count": 0,
  "delivery": {
    "enabled": true,
    "sent": 0,
    "duplicates_blocked": 0,
    "daily_cap_blocked": 0,
    "ordinary_digest_blocked": 0,
    "suppressed_by_pause": 0,
    "paused_until": ""
  },
  "source_status": {}
}
```

Systemd evidence:

```text
systemctl is-enabled telegram-utd-watch.timer -> enabled
systemctl is-active telegram-utd-watch.timer -> active
NEXT Thu 2026-09-03 17:05:43 CEST
LAST Thu 2026-09-03 16:20:20 CEST
```

## Onboarding State

Confirmed UTD profile was not present at enablement time:

```json
{"profile_loaded": false}
```

A confirmation-gated UTD onboarding draft was sent to the operator through the
existing Telegram `/utd` handler on 2026-09-03. This creates only a draft/preview;
the confirmed profile remains unchanged until the operator explicitly confirms
the preview in Telegram.

## Code Corrections In This Enablement Slice

- UTD delivery:
  - sidecar-only 24h pause feedback suppresses delivery without profile mutation;
  - ordinary non-urgent digest is capped to one digest per local UTD day;
  - delivery result exposes pause/digest suppression counters;
  - live CLI now defaults to `AGENT_DB_PATH` and the shared UTD sidecar;
  - live CLI can show sanitized candidates and calibration summaries.
- Telegram/PRM UX:
  - current external-fact boundary no longer dumps historical archive snippets or URLs;
  - hard current boundary applies only when the answer gate is blocking, not for archive answers with a freshness caveat;
  - free-text `сохрани/следи` follow-ups use existing confirmation callbacks when context exists and otherwise show a no-write preview;
  - volatile dialog state preserves topic, project, pending action and direct-only filter;
  - explicit user project names are not replaced by inferred project-fit names;
  - direct-only/no-direct follow-ups do not reuse partial/adjacent sources as project or brief support;
  - `AI adoption` relevance excludes animal/pet adoption collisions.
- Product eval:
  - expanded product UX eval simulator and deterministic checks for the above flows;
  - final 50-case `codex-exec` judge run used `gpt-5.6-terra` with medium reasoning.

## Verification

Passed:

```bash
PYTHONPATH=src python3 -m pytest \
  tests/test_prm_intent_archive_contract.py \
  tests/test_prm_application.py \
  tests/test_prm_utd_dispatch.py \
  tests/test_prm_product_ux_eval.py \
  tests/test_external_watch_delivery.py \
  tests/test_handlers.py::TestHandlers::test_telegram_current_fact_answer_first_boundary \
  tests/test_handlers.py::TestHandlers::test_current_fact_refusal_precedes_project_decision_renderer -q
```

Result: `53 passed`

Passed:

```bash
PYTHONPATH=src python3 tools/prm_product_ux_eval.py \
  --provider none --max-judge-cases 50 --dialogue-window-turns 4 --progress-every 0
```

Result: `deterministic_pass`, `50 cases`, `200 turns`, `0 deterministic failures`

Passed:

```bash
PYTHONPATH=src python3 tools/prm_product_ux_eval.py \
  --provider codex-exec --allow-provider-egress \
  --model gpt-5.6-terra --provider-reasoning-effort medium \
  --max-judge-cases 50 --dialogue-window-turns 4 \
  --progress-every 5 --partial-every 10 --provider-timeout 120 \
  --abort-provider-failures 5
```

Result:

```json
{
  "status": "needs_human_review",
  "case_count": 50,
  "turn_count": 200,
  "judged_count": 50,
  "provider_failure_count": 0,
  "deterministic_failure_case_count": 0,
  "unsafe_or_overconfident_count": 0,
  "privacy_boundary_violation_count": 0,
  "notification_noise_count": 0,
  "one_bot_fragmentation_count": 1,
  "lost_context_count": 7,
  "would_user_know_next_step_rate": "50/50",
  "safety_boundary_score": 4.98,
  "one_bot_coherence_score": 4.18,
  "notification_relevance_score": 4.72
}
```

The LLM judge remains advisory. The remaining `needs_human_review` status is due
to style and cognitive-load scores below the configured floor, not due to safety,
privacy, delivery noise, provider failures, or current-fact overconfidence.

Passed:

```bash
PYTHONPATH=src python3 tools/test_tiers.py focused-prm
PYTHONPATH=src python3 tools/test_tiers.py retrofit-boundaries
PYTHONPATH=src python3 tools/playbook_validate.py --root . --check tasks --check references
git diff --check
```

Results: `217 passed`, `81 passed`, `errors=0 warnings=0`, no diff whitespace errors.

## Remaining Dogfood Boundary

The live timer is active, but no UTD candidates will be fetched or delivered
until the operator confirms the UTD profile draft. After confirmation, the next
timer tick will poll only confirmed official sources and deliver at most the
ranked/capped relevant updates allowed by the delivery policy.

