# PRM combat evaluation — 2026-09-18

Status: deterministic local gate passed; not a pilot, dogfood, production or
model-judge approval.

## Scope

The run exercised the product claims with synthetic fixtures and disposable
SQLite databases only: archive routing and answer boundaries, multi-turn PRM
dialogue continuity, confirmation-gated memory actions, UTD onboarding/profile
preview, candidate ranking/rendering, feedback, pause handling and delivery
guards. No Telegram message, live fetch, provider request, private archive
export or production database write was allowed.

## Final evidence

| Gate | Result |
| --- | --- |
| `python3 tools/test_tiers.py focused-prm` | 296 passed in 51.40s |
| `python3 tools/prm_mat_eval.py --check all` | passed (routing plus replay/SSRF holdouts) |
| `product_rag_answer_gate_eval` | 50 rows; no-answer and external-verification-boundary accuracy 1.0 |
| Full product UX corpus | 260 cases, 980 turns; 0 deterministic failures |
| `playbook_validate` / `git diff --check` | 0 errors / clean |

The full UX run wrote only temporary artifacts under `/tmp` and used a freshly
migrated disposable `AGENT_DB_PATH`. Its provider was `none`: the model judge
was deliberately not invoked.

## Defects found and closed during this run

1. The UX evaluator did not isolate `AGENT_DB_PATH`; it now always uses a
   disposable migrated database, including direct one-case simulation.
2. Its project-context expectation lost context for confirmation follow-ups;
   the corpus now asserts the intended inherited project context.
3. Preview and pause-feedback checks were tied to brittle copy fragments;
   they now validate the actual safety contract markers.
4. UTD category routing treated `international` as an `intern` match; the
   career marker now matches complete internship forms. Additional explicit
   UTD intent markers and safety-first mixed-category labels are covered.
5. The RAG answer-gate CLI rejected valid absolute temporary report paths;
   it now reports either repository-relative or absolute paths correctly.

## Remaining evidence boundaries

- A model judge remains advisory and requires a separate, explicit egress
  decision; it may receive only redacted synthetic transcripts.
- Visual HTML review is prepared by `PRM_VISUAL_EVAL.md`; PNG/browser capture
  requires a separately approved local renderer.
- Product usefulness, source freshness in the real environment and delivery
  behaviour still require the human-approved bounded pilot packet. This run
  creates no authority to start it.
