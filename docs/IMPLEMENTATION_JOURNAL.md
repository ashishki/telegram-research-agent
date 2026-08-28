# Implementation Journal

Status: active
Last updated: 2026-08-16

Historical entries are preserved in `docs/archive/pre_retrofit_2026-08-16/IMPLEMENTATION_JOURNAL.pre-retrofit.md`.

## 2026-08-16 — RFX repository retrofit started

Baseline repository SHA: `5dfd38660b7d8d24998b4dcdf801c419c1dc8f7c`.

Created:

- archive branch `archive/pre-prm-retrofit-2026-08-16`;
- work branch `refactor/prm-repository-retrofit`;
- concise current architecture, tasks, handoff and evidence index;
- pre-retrofit document archive.

The retrofit uses a strangler boundary: active PRM interfaces move to a compact application service while report-era and historical commands remain explicit compatibility surfaces until caller migration and operator smoke evidence permit deletion.

No runtime behavior, production data, provider boundary or installed systemd unit was changed by the documentation-consolidation step.

## 2026-08-28 — UTD external-watch P0 preparation and retrofit review

Completed the repository-owned preparation only: ADR-008, a sanitized
50-slot evaluation inventory, a no-I/O manifest validator, and the RFX deep
review. No UTD endpoint was called, no collector/timer/sidecar was created,
no Telegram message was sent, and no canonical database was changed.

The review corrected stale branch/ref documentation, an ADR-005 filename
collision, and the focused-test tier's reference to a removed test module.
RFX-8 operator smoke evidence, runtime parity evidence, real sanitized source
samples, independent fixture labels, P1 approval, and all dogfood/release
claims remain human-owned gates.
