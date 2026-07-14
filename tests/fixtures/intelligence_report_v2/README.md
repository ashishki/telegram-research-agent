# Report V2 regression fixtures

This directory contains the consolidated IRX-13 fixture manifest for the Report
V2 release candidate.

The manifest is intentionally a structured contract registry, not a dump of
private report output. It references only synthetic or sanitized fixtures and
records the scenario coverage, contract versions, expected structured outcomes,
redaction policy, and the desktop/mobile visual-regression procedure.

Rules:

- raw Telegram channel content is excluded;
- generated private Brief/Atlas reports are excluded;
- structured assertions must pass before any pixel snapshot is considered;
- full HTML goldens are avoided except for bounded sanitized component HTML;
- visual hashes must not be recorded silently.

Screenshot harness:

```bash
PYTHONPATH=src python3 scripts/report_v2_visual_snapshots.py \
  --manifest tests/fixtures/intelligence_report_v2/irx13_fixture_manifest.v1.json \
  --viewports 1440x1000 375x1000
```

The harness requires the Python Playwright package and a local Chromium browser.
If those prerequisites are missing, it exits non-zero with an explicit message.
That failure is intentional: IRX-13 must not claim visual evidence without a
deterministic browser environment.

Snapshot update policy:

1. Run the focused IRX-13 structured tests first.
2. Run the harness at exactly 1440x1000 and 375x1000.
3. Review screenshots for evidence, editorial, responsive-layout, and redaction
   regressions.
4. Commit approved SHA-256 hashes in `visual_regression.approved_snapshot_hashes`
   and change `baseline_status` to `recorded` only after review.
5. Treat browser, OS, and font changes as baseline changes requiring the same
   review.
