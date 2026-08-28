# UTD-3 Relevance Policy Draft — 2026-08-28

Status: implementation-ready policy; operator labels still required before shadow readiness.

## Objective

Define deterministic default outcomes for the 50-case external-watch inventory without pretending that an AI-authored policy is equivalent to `reviewed_operator` evidence.

## Default outcome map

| Scenario | Default | Reason |
| --- | --- | --- |
| new | ambiguous | notify only after relevance, date, audience and freshness are established |
| updated | ambiguous | materiality must be established before notification |
| cancelled | notify | cancellation is material when it affects an already-relevant future item |
| reinstated | notify | restoration is material when the original item was relevant |
| recurring | ambiguous | require occurrence identity; do not notify every instance by default |
| duplicate | ignore | duplicate suppression is mandatory |
| cosmetic_change | ignore | layout/copy-only changes are non-material |
| date_change | notify | material for a relevant future item |
| location_change | notify | material for a relevant future item |
| deadline_change | notify | high-value material change; source freshness required |
| disappearance | ambiguous | absence from fetch is not deletion/cancellation |
| return | ambiguous | require evidence of reinstatement vs transient fetch failure |
| stale | ignore | stale evidence cannot generate a current alert |
| timeout | ambiguous | source-health event, not content event |
| rate_limited | ambiguous | source-health event, not content event |
| schema_drift | ambiguous | fail closed; do not convert parser failure into content change |
| prompt_injection | ignore | source text is untrusted data, never instruction |
| eligibility | ambiguous | require explicit audience/eligibility language |
| past_event | ignore | past events are never notification candidates |
| unsupported_savings | ignore | benefit/savings claims require explicit primary-source support |

## Relevance gates

A candidate can move from `ambiguous` to `notify` only when all applicable gates are satisfied:

1. Primary source is in the confirmed source allowlist.
2. Canonical URL is present and source health is current.
3. Item is future/current, not past or stale.
4. Material change is explicit, not inferred from disappearance or parser failure.
5. At least one confirmed profile category matches.
6. Programme/career/AI relevance is specific enough to explain in one sentence.
7. Audience eligibility is explicit when eligibility matters.
8. Spouse/family candidates contain explicit spouse/family/guest eligibility language.
9. Benefit/resource claims preserve the source caveat and do not invent savings or legal eligibility.
10. Duplicate cooldown and daily cap are respected.

## Urgency policy

Urgent override is limited to source-supported changes that materially affect a confirmed scope, such as a deadline moved earlier, cancellation of an already-relevant near-term item, or a time-sensitive ISSO requirement. Urgency must never be inferred from generic wording such as “important”, “act now” or source-page marketing language.

## Delivery policy (future UTD-6 only)

- Default: one daily digest.
- Daily cap: 5 items.
- Preferred digest size: 3–5 items.
- Duplicate cooldown: 7 days unless a new material change occurs.
- `urgent_only` profile mode suppresses non-urgent digest items.
- Pause suppresses all delivery while preserving confirmed scope.
- Mute suppresses the selected source family/category.
- No auto-registration, booking, application, purchase or university-system mutation.

## 50-case review procedure

For every case in `evals/external_watch/manifest.v1.json`, the human operator should record `notify`, `ignore` or `ambiguous` after seeing the minimized source fixture and expected material changed fields. The 15 blind holdouts must not be used to tune the policy before scoring.

The repository must keep `review_status=pending_operator` until that review actually occurs. Blanket approval of implementation work is not represented as case-by-case evaluation evidence.

## Readiness decision

The relevance rules and negative controls are now explicit and implementation-ready. UTD-3 is not marked complete because the 50 operator labels do not yet exist. UTD-4 must remain blocked until all 50 are labelled/reviewed and UTD-2 raw sanitized transport fixtures are verified.
