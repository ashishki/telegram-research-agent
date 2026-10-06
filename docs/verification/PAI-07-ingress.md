# PAI-07 local engineering receipt

2026-10-06. Base aed2431; assigned branch
docs/personal-assistant-blueprint-playbook-20260918. Scope authorized by ADR-014.

Real Telegram polling has an explicit durable ingress route. Immutable inbox
input and queue admission commit together; acknowledgement/offset advancement
follow that commit. Duplicate update IDs reuse the same job; changed content
under the same ID fails closed. A capacity failure rolls back the inbox and
leaves the offset available for replay. Text, voice references/transcripts and
job callbacks require the exact private owner tuple. Arbitrary action callbacks
remain unavailable. Intake performs no transcription or research.

The separate assistant worker calls PersonalResearchAssistant with durable,
request-scoped conversations and publishes an immutable request-bound result
through the fenced queue. Cancellation during an in-flight computation rejects
its later completion. Status/result/cancel survive reconstruction. Explicit CLI
configuration connects polling, one-shot worker and job controls; no target or
service is selected implicitly. Foreground authorization decisions are not
serialized as background authority. Real model/source/delivery wiring remains
in later cards. Raw voice without an authorized resolver returns unavailable.

Changed: src/bot/bot.py, src/prm/cli.py, src/prm/storage/jobs.py,
src/prm/runtime/worker.py, new src/prm/runtime/ingress.py and
tests/test_pai_ingress_jobs.py. Existing digest workers filter their own kind.

Verification:

```
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q tests/test_pai_ingress_jobs.py tests/test_prm_bot_dispatch.py tests/test_callbacks.py tests/test_prm_cli.py tests/test_pai_workers.py
```

51 passed in 39.76s; zero skips/failures. Includes actual isolated PostgreSQL,
real polling during a blocked application, offset replay, actual application
answers, explicit CLI composition, owner isolation and worker fencing. Initial
new-card debug run: 11 passed in 9.82s. First broader run before the two CLI
extensions: 50 passed in 40.44s. No provider/network send occurred.

`python3 tools/playbook.py --check-pin`: passed.
`python3 tools/check_personal_assistant_plan.py`: passed.
`python3 tools/check_pai_plan.py`: 32 packets, 69 requirements, 10 scenarios;
22 future test files absent, explicitly pending. `git diff --check`: passed.

Independent phase-B Mimo review remains pending: call #21 had no valid
completion. This receipt is local_verified, not independent/human/live/release
acceptance. No formal task/design approval fields changed. Next PAI-08:
read docs/PA_IMPLEMENTATION_TASKS.md#pai-08 and implement durable scheduler.
