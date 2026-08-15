# PRM-QA Quality Gap Audit

Status: active
Date: 2026-08-15

Baseline inspected at repository SHA `516fc7206f99b58e6d276585c3dba6d87a39392f`
and Playbook SHA `965612aa463fca1a35a55104633d0e09da33d615`.

## Verified Gaps

- Retrieval: the approved local vector sidecar is `local_hashing_text_vector.v1`,
  based on word, word-bigram, and character n-gram hashing. It is not a trained
  multilingual dense embedding model.
- Vector participation: hybrid archive retrieval defaulted to
  `fallback_on_fts_miss`, so vector search was skipped whenever FTS returned
  any result.
- Query planning: `memory_research.py` contains many hand-authored domain
  expansions. PRM-QA adds a generic policy layer and evaluates legacy expansion
  behavior instead of expanding the domain dictionary.
- Evidence quality: relevance, directness, independence, corroboration,
  freshness, primary-source status, project fit, and operator interest were not
  represented separately.
- Grounding eval: the older live UX judge saw question, answer, and source
  count, not exact supporting snippets; its `grounded` field is presentation
  judgment, not entailment proof.
- Synthesis verifier: the bounded PASS/FAIL verifier is useful fail-closed
  filtering, not independent grounding proof.
- Project decisions: recent synthetic eval identified project-decision answers
  as weakest. Ambiguous “мой проект” prompts were a test-design and product
  ambiguity issue.
- User value: automated evals measured routing, structure, and synthetic proxy
  outcomes; real product value still requires future operator feedback.
- Debuggability: PRM-QA adds gitignored failed-case traces with route,
  retrieval, evidence-quality, claim ledger, final verification, and failure
  codes.

## Boundary

No production DB contents, provider calls, live Telegram jobs, live web research,
external embeddings, hosted vector services, dogfood start, or release claim are
authorized by this audit.
