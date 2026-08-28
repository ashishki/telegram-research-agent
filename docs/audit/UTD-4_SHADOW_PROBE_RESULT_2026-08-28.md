# UTD-4 Bounded Shadow Collector Result — 2026-08-28

Status: implementation_complete_with_residual_human_quality_gate

## Scope

A bounded real-source shadow probe was run against the three approved public source families using an ephemeral synthetic confirmed UTD profile and an ephemeral sidecar SQLite database. The production PRM database was not copied, opened, migrated or mutated. No Telegram message, provider call, timer enablement, authenticated UTD system or credential was used.

## Source and safety result

All three allowlisted sources returned healthy results during the final probe:

- `calendar`: ok
- `isso`: ok
- `basic_needs`: ok

The fetch boundary is HTTPS-only and host-allowlisted, rejects URL credentials, IP literals, non-default ports, unsafe DNS resolution, redirects, unsupported content types and oversized responses, and treats HTTP 429 as source health rather than content change.

The sidecar preserves Localist event/instance identity and source timezone offsets, records new/updated/cancelled/reinstated state idempotently, and does not convert source failure, rate limit or schema drift into disappearance/deletion.

## Runtime finding and correction

The first bounded live probe exposed an architectural coupling: importing `assistant.utd_profile_store` executed the heavy `assistant` package initializer and pulled in report-era/LLM dependencies. The collector was corrected to use `external_watch.profile`, a minimal SQLite `mode=ro` profile reader with expiry and tombstone handling. This removed LLM/provider dependencies from the sidecar runtime.

## Relevance calibration

Initial live snapshot:

- sidecar items / first-run changes: 102
- initially marked relevant: 82
- second run changes: 0

That first relevance ratio was too broad for the intended low-noise assistant UX. Generic `research` and `engineering` signals were therefore removed as standalone matches and the policy was tightened around source-aware high-signal evidence and confirmed profile phrases.

Final calibrated live snapshot:

- sidecar items / first-run changes: 102
- relevant changes: 32
- relevant category observations: program 17, career 13, AI 2, ISSO 3, benefits 4, spouse/family 1 (categories can overlap)
- future user-facing shadow candidates after materiality/priority/cap: 5
- urgent candidates among those five: 3
- second run changes: 0
- second run candidates: 0

The final second pass demonstrates idempotency on the same live source state. Candidate selection respects the confirmed daily cap with a hard maximum of five and supports `urgent_only`; it is shadow-only and has no delivery path.

## 50-case policy coverage

`tools/utd_policy_eval.py` gives every one of the 50 manifest scenarios a deterministic **proposed** `notify`, `ignore` or `ambiguous` outcome while explicitly setting `human_labels_added=false` and `holdouts_used_for_tuning=false`. This is implementation evidence only. It does not change `review_status=pending_operator` and is not represented as human/gold evaluation evidence.

## Post-probe cleanup

The temporary GitHub Actions workflows used only for one-shot source capture and bounded shadow probing were removed after evidence collection. No UTD GitHub Actions workflow remains that automatically performs public source capture or shadow polling. The systemd shadow timer remains a checked-in disabled template and was never enabled or started.

## Decision

UTD-4 collector implementation and bounded real-source verification are complete. The collector remains non-deployed and the systemd timer remains a disabled template. UTD-5 precision/recall or notification-readiness claims remain blocked on real human review labels; Telegram delivery remains out of scope until the later delivery gate and review are satisfied.
