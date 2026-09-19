# Personal Assistant — Owner Intent Brief

Status: owner-requested product direction captured; exact design approval pending.
Date: 2026-09-18
Canonical requirements: `docs/PERSONAL_ASSISTANT_SPEC.md`.

## Pain and current workaround

Information and obligations are scattered across Telegram reading, public web,
project repositories and personal university/mail/calendar sources. The current
bot has useful archive/evidence boundaries but does not yet feel like a natural
personal assistant. The owner manually switches tools, asks repeated queries,
reads source lists and reconstructs context and weekly priorities.

## Full desired result

One assistant with Chat / Search / Brief / Watch / Act. Normal conversation and
followups; real AI search across permitted archive, web and connected data;
beautiful useful weekly and topical reports in Telegram, private mobile HTML,
PDF and Markdown; confirmed subscriptions/reminders; Academic Inbox integrated
with mail/calendar/Canvas; precise approved actions; controllable memory;
voice/documents; measured quality-first model selection and reliable recovery.
The owner explicitly does not want the plan limited to an MVP.

## Product proof

The first proof is a complete actual user journey, not presence of a module:
ask naturally -> use the correct permitted sources -> get a useful grounded
answer -> refine or turn it into a versioned briefing/action. Full completion
requires the requirement-to-path/test/review/user-evidence matrix described in
spec section 13. Latency, accuracy and cost figures in the spec are proposed
acceptance targets, not measured results.

## Resources and boundaries

The owner is willing to provide available access and models. Exact accounts,
provider scopes, data-egress permission, budgets and live schedules remain
explicit decisions; willingness is not a configured grant or infinite spend.
Preserve one bot, existing canonical archive, privacy and confirmation rules.
The current session only documents, updates tooling and publishes changes.

## Development

Mode: Standard. Proposed planning depth: designed_slices.
Execution: Codex Direct with independent, risk-targeted read-only review.
Design: `docs/design/PA.md` + `docs/design/PA.design.json`.
Current regression command: `python tools/test_tiers.py focused-prm`.
Known baseline failure must remain visible until its cause is corrected.
Full verification uses `python tools/playbook.py verify_project --root .`;
no release claim without current passing project and real-user evidence.
