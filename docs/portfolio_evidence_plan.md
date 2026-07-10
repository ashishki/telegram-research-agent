# Portfolio Evidence Plan

Version: 1.0
Last updated: 2026-07-10
Status: supporting portfolio-readiness plan

This plan defines what must exist before the project is presented as an
8.5-9/10 Personal AI / Knowledge Intelligence System. A component is not
portfolio evidence just because it exists in code; it needs tests, artifacts,
dogfood outcomes, or clear failure analysis.

## Current Evidence-Based Score

Current score: **6.8/10**.

Evidence behind the score:

- broad implemented codebase with ingestion, knowledge atoms, idea threads,
  report generation, feedback, Hermes/PI facade, and Radar bridge;
- focused tests for many subsystems;
- committed W28 visual fixture;
- no open GitHub PRs/issues found via connector on 2026-07-10;
- no four-to-eight week dogfood evidence series yet;
- no sanitized reproducible demo dataset yet;
- product docs were previously inconsistent about active roadmap and main
  surface.

## Portfolio Readiness Gate

| Gate | Status | Current evidence | Required evidence before `evidenced` |
|---|---|---|---|
| Product evidence | `partial` | one W28-style dogfood/manual eval trail exists locally; dogfood helper code exists | 4-8 weekly scorecards, decisions/actions changed, rejected/deferred examples, overload reduction, project improvements, learning outcomes |
| Intelligence correctness | `partial` | report contract tests, quote/evidence card gates, W28 fixture | canonical SourceObservation/EvidenceItem/Claim contract, contradiction/negative evidence fixtures, calibrated confidence report, documented failures |
| Engineering quality | `partial` | modular Python code, SQLite helpers, tests, bounded Hermes tools, systemd docs | deterministic local demo, CI proof, cost/latency telemetry, graceful degradation tests, sidecar versioning rules |
| Assistant quality | `partial` | read-only facade/tools/chat tests | Hermes answer eval dataset, current/stale artifact detection, feedback provenance answers, insufficient-evidence behavior, no hidden mutation audit |
| Product surfaces | `partial` | Brief/Atlas split renderer and tests | decision-first Brief, navigable Atlas v2, Project Intelligence, Learning Dashboard, Radar Gate integration, source navigation tasks |
| Portfolio presentation | `not started` | README and docs | sanitized demo dataset, screenshots, architecture/domain/sequence diagrams, evaluation report, 5-minute demo script, case study, public/private boundary |

No gate is `evidenced` without a concrete committed artifact, test, or dogfood
scorecard.

## Evidence Artifacts To Produce

### Product Evidence

- `docs/dogfood_scorecards/YYYY-WNN.md` or sanitized equivalent.
- Weekly Verified Decision Impact table.
- Examples of accepted, rejected, deferred, and verify-first decisions.
- Experiment logs with success/kill criteria and outcomes.
- Time-to-understand measurements for Brief and Atlas tasks.

### Correctness Evidence

- `tests/fixtures/intelligence_contract/` with source/evidence/claim/thread
  cases.
- Eval report covering unsupported claim rate, quote coverage, contradiction
  visibility, and source independence.
- Failure taxonomy with at least five real or fixture-backed failure cases.

### Engineering Evidence

- Reproducible local demo command.
- CI badge or CI run evidence.
- Cost/latency summary for weekly generation.
- Sidecar schema version compatibility tests.
- Graceful missing-artifact tests for Radar, Brief, Atlas, and Hermes.

### Assistant Evidence

- Hermes answer eval dataset.
- Grounded answer scorecard.
- Examples of insufficient-evidence answers.
- Feedback provenance examples showing source, confirmation state, and effect
  window.
- Explicit no-mutation proof from tool catalog tests.

### Surface Evidence

- Sanitized sample Weekly Brief.
- Sanitized sample Knowledge Atlas.
- Project Intelligence sample for one active repo.
- Learning Intelligence sample showing a skill moved beyond reading.
- Radar Gate sample showing `investigate` or `reject` due to evidence gaps.

### Presentation Evidence

- Architecture overview diagram.
- Domain model diagram.
- Brief generation sequence diagram.
- Hermes answer sequence diagram.
- 5-minute demo script.
- Case study for one weekly decision or project change.
- Screenshots with private data removed.

## Portfolio Narrative

The final case study should answer:

1. What problem did the operator have?
2. Why generic digest/RAG/chatbot approaches were insufficient?
3. What domain model makes the system trustworthy?
4. How does the Weekly Brief reduce decision time?
5. How does Atlas preserve temporal understanding?
6. Why Hermes is bounded and not source of truth?
7. How are feedback and operator context used safely?
8. How does Radar avoid false product validation?
9. What did dogfood change in real decisions, projects, or learning?
10. What failed, and how did evaluation catch it?

## Demo Requirements

Minimum demo:

- runs locally without secrets;
- uses sanitized fixtures only;
- generates Brief and Atlas;
- loads Hermes over curated objects or runs a deterministic answer fixture;
- shows one Radar `investigate` or `reject` gate;
- shows one feedback event and one ranking/provenance explanation;
- includes expected runtime and cost notes.

Do not include raw Telegram exports, `.env`, private reports, or operator-only
notes in the demo.

## Evidence Review Schedule

- After PR 1: correctness fixture review.
- After PR 2: personalization and feedback provenance review.
- After PR 3: Brief/Hermes/Radar usability review.
- After four weekly runs: product evidence review.
- After six to eight weekly runs: portfolio readiness review.

## Stop Conditions

- Any build/product recommendation from context-only evidence.
- Any uncited top claim in a portfolio sample.
- Any hidden assistant mutation.
- Any private source leakage in committed artifacts.
- Any README claim of dogfood value not backed by scorecards.
