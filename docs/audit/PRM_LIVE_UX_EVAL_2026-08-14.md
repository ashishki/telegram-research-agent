# PRM live UX evaluation — 2026-08-14

`tools/prm_live_ux_eval.py` provides a repeatable 100-scenario UX regression
harness. It generates the scenarios itself, retrieves from the local archive,
uses the active LLM router when explicitly enabled, renders the Telegram answer
surface, and applies a bounded LLM UX judge. It sends no Telegram messages and
stores only aggregate, fingerprinted receipts under gitignored `data/events/`.

The first live run completed all 100 unique scenarios in 20 five-case batches.
It used 200 provider calls (maximum 15 per batch, one retry per call) and left
the production `llm_usage` count unchanged at 819. No raw questions, answers,
sources, chat ids, judge free text, or Telegram corpus were committed.

Result: this is a deliberately failing baseline, not a release claim. The
strict LLM judge scored 1.34/5 on average and passed 0/100 current thresholds.
The run exposed a concrete router defect: all 25 project-decision scenarios
were routed to editorial brief by the LLM router. A deterministic grounded
research guard was added and covered by focused tests. The judge's high
technical-leak rate conflicts with the deterministic renderer leak check, so
its calibration is an open product-quality task rather than an accepted fact.

Focused verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_prm_live_ux_eval.py tests/test_handlers.py -q
67 passed in 6.72s
git diff --check
```

The required read-only deep review was run before live egress. Its effective
reviewer assignment was `unverified`; it found and the implementation fixed
the egress approval, usage-write suppression, retry/call budget, receipt
privacy/path, and staticmethod restoration findings. This run is manual
evaluation evidence only; it is not dogfood or a release claim.

Follow-up `8b564b2` keeps verification-required answers deterministic and adds
the existing bounded professional contract to approved synthesis: sanitized
short answer, up to four claim/citation pairs, one recommended action, and up
to three uncertainty items. Field caps are enforced in focused tests; no raw
DTO, internal path, ID, or telemetry field is sent.

The 2026-08-15 synthesis quality filter adds one bounded verifier call. A full
100-case live run therefore permits up to 400 provider calls: router,
synthesis, verifier, and judge per case. The evaluator enforces that cap and
does not treat budget exhaustion as a valid quality result.

## 2026-08-15 fixed-corpus follow-up

A complete 100-case run of the generated corpus completed with 301 bounded
provider calls, no Telegram sends, no durable writes, and aggregate-only
gitignored receipts. The pre-calibration judge reported 2/100 passes and an
average 1.57/5, including 64 alleged technical leaks and 83 alleged grounding
failures. These are diagnostic baseline signals, not a release or product
quality claim: the judge rubric was demonstrably over-broad about normal source
URLs, local-only boundaries, and technical subject vocabulary.

The evaluator rubric was corrected before any comparison rerun. It now treats
those normal user-facing elements as valid, requires a clear local-boundary
refusal for current-fact questions, and records `action_oriented` as tracked
only rather than a universal pass/fail gate. The corrected rubric passed
focused tests and required read-only re-review; effective reviewer assignment:
`unverified`. No raw questions, answers, sources, chat IDs, or judge prose are
stored in this document.

After the deterministic current-fact renderer was changed to lead with an
unambiguous refusal, state that external verification was not run, and label
archive material historical, a targeted regenerated 25-case current-fact run
completed 25/25 with an average calibrated judge score of 4.04/5. It used 50
bounded provider calls, sent no Telegram messages, made no durable writes, and
stored only gitignored aggregate receipts. This is a scoped regression result,
not a release claim or dogfood evidence.
