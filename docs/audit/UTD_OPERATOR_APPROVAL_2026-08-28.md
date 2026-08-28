# UTD Operator Approval — 2026-08-28

Status: explicit shadow-only operator approval recorded

The human operator explicitly delegated action on the user's behalf and requested that the assistant do the maximum useful work. This approval is interpreted as permission to cross the previously blocked UTD-4 gate for **manual/public source capture and real source-bounded shadow polling only**.

Approved:
- public allowlisted UTD source capture;
- sanitized evidence artifacts;
- real shadow polling with no user-facing delivery;
- sidecar-only derived state;
- source health and diff evaluation.

Not approved by this record:
- Telegram notification delivery;
- production PRM DB migrations or writes by the collector;
- credentials, authenticated university systems, 12twenty mailbox access, registration/apply/book/purchase actions;
- provider/raw archive egress;
- representing AI-generated relevance labels as human operator labels;
- dogfood/release readiness claims.

This record exists to make the UTD-4 polling boundary auditable. Human-only label/sign-off requirements in `docs/REVIEW_POLICY.md` remain human-only.