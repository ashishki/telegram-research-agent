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
