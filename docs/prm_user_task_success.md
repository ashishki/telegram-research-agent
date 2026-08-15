# PRM User Task Success

Status: active
Date: 2026-08-15

North-star metric: successful operator task completion.

Automated PRM-QA reports include only a synthetic task-success proxy. Real value
requires future operator behavior:

- useful / partial / miss feedback;
- rephrase required;
- saved note;
- watched topic;
- action or experiment created;
- project decision changed;
- meaningful manual research time saved;
- repeated usage.

Normal Telegram answers show `Полезно`, `Частично`, and `Мимо`. Partial/miss
feedback can add reasons: wrong sources, too general, wrong project, no useful
action, too long, or weak evidence.

Private interaction receipts are written under `data/evals/private/prm_qa/` and
are gitignored. They store metadata, hashes, retrieval policy, evidence summary,
claim metrics, and feedback state, not raw prompts or raw archive bodies.
