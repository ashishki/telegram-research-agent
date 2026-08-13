# PRM Assistant Runtime

Status: manual-test runbook
Last updated: 2026-08-12

The current `telegram-prm-assistant.service` is an operator-controlled test
runtime. Ordinary Telegram text and voice are the default
entrypoint; `/research`, `/brief`, and `/chat` are fallback controls.

For local inspection use `PYTHONPATH=src python3 src/main.py memory status`.
Do not change service state, environment flags, provider egress, or systemd
units under this runbook without explicit operator approval.

See `docs/PRODUCT_OPERATING_MODEL.md` for runtime truth and
`docs/operator_quickstart.md` for daily use.
