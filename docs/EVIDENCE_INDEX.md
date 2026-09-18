# Evidence Index

Status: active
Last updated: 2026-09-17

Historical evidence is preserved in `docs/archive/pre_retrofit_2026-08-16/EVIDENCE_INDEX.pre-retrofit.md` and Git history.

## Current baseline

- latest audited code: `cee8baae3b8a41f571bd689f2dadf7e6e981863f`;
- search/news audit: `docs/audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md`;
- task registration (not implementation/review): `docs/audit/PRM_SEARCH_NEWS_TASK_REGISTRATION_2026-09-17.md`;
- retrofit baseline: `5dfd38660b7d8d24998b4dcdf801c419c1dc8f7c`;
- archive: preserved as the remote pre-retrofit archive branch (discover with
  `git branch -r`); it is intentionally not a workspace path;
- active integration ref: `master`;
- Eval V2 audit: `docs/audit/PRM_EVAL_V2_QUALITY_PASS_2026-08-15.md`;
- retrieval ADR: `docs/adr/ADR-005-prm-qa-selected-retrieval-policy.md`;
- ADR numbering remediation: `ADR-005` is retrieval policy, `ADR-006` is the
  intent-first contract, and `ADR-007` is local deep research; historical
  duplicate filenames were renamed without changing their decisions.
- public regression reports: `evals/prm_qa/`;
- operator usefulness: not yet proven; controlled smoke review remains required.
- historical delivery receipt: UTD timer enabled on 2026-09-03 pending profile
  confirmation; current service/profile state was not observed by this audit.
- PRM-SN task/review registration is documentation, not implementation,
  a completed Terra review, or permission to start dogfood.

## Retrofit evidence

| Item | Location | State |
| --- | --- | --- |
| Strategy and deletion rules | `docs/retrofit/RFX_REPOSITORY_RETROFIT.md` | current |
| Active architecture | `docs/ARCHITECTURE.md` | current |
| Active task queue | `docs/tasks.md` | current |
| Pre-retrofit docs | `docs/archive/pre_retrofit_2026-08-16/` | preserved |
| Deep review | `docs/retrofit/RFX_DEEP_REVIEW.md` | complete with human-only residual gates |
| Focused PRM tests | local 2026-08-28 verification | see RFX deep review |
| Retrofit boundary tests | local 2026-08-28 verification | see RFX deep review |
| MAT safety | local 2026-08-28 verification | see RFX deep review |
| Playbook validation | local 2026-08-28 verification | see RFX deep review |
| UTD controlled live-watch enablement | `docs/audit/UTD_LIVE_DOGFOOD_START_2026-09-03.md` | enabled; no source polling or delivery before profile confirmation |
| PRM product UX advisory judge | `docs/audit/PRM_PRODUCT_UX_JUDGE_2026-09-03.md` | 50 cases / 200 turns; human review remains for style and cognitive load |

## Evidence rules

- focused tests are not a full-suite claim;
- automated silver evals are regression evidence, not proof of usefulness;
- private questions, post bodies, provider payloads and local paths are not public evidence;
- deleted code remains recoverable from the archive branch and Git history.
