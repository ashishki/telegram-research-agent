# Public Evidence Boundary

This directory contains only privacy-reviewed public evidence. Generated
operator reports, raw Telegram content, sessions, credentials, and private
feedback do not belong here.

Current public dogfood status is recorded in
[`public_dogfood_status.json`](public_dogfood_status.json). Its scope is public,
verified evidence: the current count is 0 of the required 4 weeks.

`public_demo_scorecard.json` is generated entirely from synthetic fixtures by
the existing deterministic scorecard logic. It demonstrates a contract and a
negative evidence gate only. It is not evidence of an operator run, user value,
changed decisions, time saved, or production reliability.

Build or verify the demo without credentials:

```bash
PYTHONPATH=src python3 scripts/public_scorecard_demo.py
PYTHONPATH=src python3 scripts/public_scorecard_demo.py --check
```
