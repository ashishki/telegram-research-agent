# Phase-C review #38 follow-through — new recheck pending

Receipt: PAI-review-continuation-38.json, reviewed c840ecc. The independent
review resolves #37's grant/Watch fixes, then retains one new P1 and two P2s.
Same bounded Mimo/OpenCode Go, thinking disabled; no human or live acceptance.

The new scheduled-delivery guard prevents a caller from omitting effect_lease
when a matching durable effect intent exists and no attempt has yet occurred.
A cancelled/expired lease remains denied; adding effect_lease=None cannot
bypass it. Existing attempt status can still be read without sending again.
Unscheduled explicit owner result reads remain separately grant-guarded.
The existing compute completion fence already prevents publication after cancel;
the next packet includes its previously omitted full JobQueue implementation.

Cancel acknowledgement now queries the actual current state and explicitly
warns that an already-started external call might continue. The real slow-polling
test still requires cancelled status, fenced completion failure, and no saved
result, while checking the new exact message instead of the old shorter string.

Multipart reconciliation checks every expected child ID, payload digest,
destination and source binding. Each unknown part needs its own scoped provider
evidence. A missing/unattempted part cannot be proved by an aggregate receipt;
the aggregate remains unknown, without sender retries. All verified parts are
needed before marking the parent sent. A real three-part synthetic case loses
the second ACK and proves that reconciling it cannot imply delivery of missing
part three. Reconciliation also checks the stored payload digest.

The strict legacy notification codec already rejects unknown/missing fields and
validates its dataclass. It still receives only declared fields; delivery now
additionally limits the rendered Watch text to 3800 characters before reservation
or transport. Source authority remains separately bound in the full stored digest.

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q -x tests/test_pai_delivery.py tests/test_pai_ingress_jobs.py
```

First attempt: collection error in 5.04 s from an implementer syntax typo in the
new cancel text. Corrected syntax; next attempt: 1 failed / 28 passed in 43.43 s
because the polling test still asserted the old acknowledgement. Updated the
exact message expectation while retaining all cancellation/no-result assertions.
Final: 34 passed in 43.53 s, zero skips/failures.

Related PAI-00 maintenance makes the existing native OpenCode route accept an
explicit --thinking-disabled flag. The wire body contains the requested mode;
requested/observed effort are distinct, and absent/non-integer/nonzero reasoning
telemetry does not become observed zero. No role types, human acceptance,
planning gate, tooling trust gate or pinned consumer were bypassed/expanded.
Initial bridge/role/guard/tier checks: 80 passed in 4.10 s; final changed-mode
checks: 57 passed in 1.73 s, zero skips/failures. Commands in controlled logs:
pai-validation-20261008/reviewer-mode.log and reviewer-mode-final.log.
The actual native tooling packet is prepared (131737 bytes, provider_call=false);
its planning decision requires human-selected depth. This remains a genuine
gate, not a fabricated role receipt. Independent source reviews continue.

Full source baseline: prior 259-case PAI observation; focused-prm 652 passed in
132.56 s before the C changes; retrofit-boundaries 150 passed in 12.29 s after
Watch source fixes. Source snapshots are preserved separately.
Next: bounded fresh #39 C recheck including complete JobQueue, then D/E/F.
