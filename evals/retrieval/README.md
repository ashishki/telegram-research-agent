# Retrieval Evaluation Candidates

Status: candidate
Last updated: 2026-07-26

This directory contains candidate retrieval queries for Personal Telegram
Research Memory. The cases are not gold evidence.

Rules:

- Agent-drafted queries remain candidates until the human operator approves the
  query, expected evidence, source citations, and no-answer expectation.
- No query in query_set_candidate.jsonl may be used as a pass/fail gold label
  without a human-approved label file.
- Private Telegram post text must not be copied into public fixtures.
- Gold labels should reference stable document identities and Telegram source
  links, not copied full post bodies.

Planned distribution:

- 8 exact known-item candidates
- 8 semantic topic candidates
- 8 case-study candidates
- 6 multi-document comparison candidates
- 6 freshness/news candidates
- 6 project or life application candidates
- 4 distractor candidates
- 4 no-answer candidates

Human-approved gold labels should be created in a separate file after PRM-1.
