# PRM bounded Telegram synthesis quality filter — 2026-08-15

The approved Telegram RAG synthesis path now applies a best-effort LLM quality
filter before returning provider-generated prose. It receives the same bounded,
sanitized synthesis context and the proposed answer; it does not receive the
raw archive, create receipts, write to SQLite, send Telegram messages, fetch
the web, or rewrite a rejected answer. Its result is not a security guarantee
or an independent citation-entailment proof.

The path is fail-closed: only the exact verifier token `PASS` permits the
generated text; lowercase, whitespace-padded, and punctuated variants are
rejected. A provider failure, malformed output, or any other verdict returns
the existing deterministic professional answer renderer instead. Both
synthesis and filter run inside usage-recording suppression.

The egress budget is explicit: synthesis allows one provider transport attempt
(at most 900 output tokens) and the filter allows one provider transport
attempt (at most 80 output tokens). Therefore one rendered answer has at most
two provider attempts in this path, with no retry backoff. The pre-existing
`PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS` and
`PRM_TELEGRAM_RAG_LLM_SYNTHESIS` flags remain required.

Focused verification (no full suite):

```text
PYTHONPATH=src python3 -m pytest tests/test_handlers.py -q
73 passed in 9.68s

PYTHONPATH=src python3 -m pytest tests/test_llm_client.py -q
10 passed in 17.68s

git diff --check
```

The required read-only deep review was completed before this implementation
continued and repeated after corrections. The runtime did not expose an
effective reviewer model/reasoning assignment, so it is recorded as
`unverified`. The initial review identified the retry/cost boundary and an
overstated independence claim; both were corrected. A later live-eval attempt
found JSON-format brittleness and the evaluator's obsolete 300-call cap. The
verifier was changed to the exact `PASS` token and the synthetic 100-case cap
to 400 calls (router, synthesis, verifier, judge); re-review found no P0/P1
actionable findings. This is implementation evidence only, not operator
validation, dogfood evidence, or a release claim.
