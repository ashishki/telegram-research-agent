# Visual product-eval packet

Use `tools/prm_visual_eval_packet.py` to create a privacy-safe visual review
slice for the personal Telegram assistant. It reuses the synthetic PRM/UTD UX
corpus: archive search, current-fact boundaries, follow-ups, confirmation,
topic editions, onboarding, notifications, feedback and lifecycle controls.

```bash
PYTHONPATH=src python3 tools/prm_visual_eval_packet.py \
  --output-dir .playbook-artifacts/prm_visual_eval --pdf
```

The default creates 36 balanced scenarios (six per surface), autonomous
Telegram-like HTML screens, optional local PDF previews when the installed
backend is compatible, `manifest.json` and
`judge_cases.ndjson`. It does not call a model, Telegram, a public source or a
provider, and does not access the personal archive.

Review each screen against: directness, source/freshness clarity, useful next
step, readable hierarchy, confirmation clarity, no technical leakage, and
notification relevance. A model judge may receive only the redacted NDJSON
after a human checks the packet. Its score is advisory until calibrated against
human labels. Do not attach real chat screenshots or private archive content.

PNG screenshots are intentionally optional: this repository does not install a
browser/rasterizer. HTML is the portable source of visual truth; PDF status is
recorded in the manifest. A local browser can capture screens at 390px mobile
width after separate tool approval.
