# PRM Evidence Quality Contract

Status: active
Schema: `prm_evidence_quality.v1`

Evidence quality is separate from relevance. Required fields:

```yaml
evidence_id:
source_url:
source_class:
source_group_id:
posted_at:
freshness_status:
relevance_score:
directness:
independence:
corroboration_count:
primary_source_status:
operator_interest:
project_fit:
support_span:
content_hash:
```

Source classes are `telegram_commentary`, `telegram_forward`,
`telegram_firsthand_case`, `official_documentation`,
`official_vendor_announcement`, `github_repository`, `research_paper`,
`company_case`, `independent_case`, and `unknown`.

Telegram reposts, duplicates, and repeated upstream claims share source groups
when deterministic metadata allows it. Unknown independence is represented as
`unknown`, never guessed.
