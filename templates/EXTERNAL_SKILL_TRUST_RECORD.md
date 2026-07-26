# External Skill Trust Record

Status: draft | approved | rejected | retired
Owner:
Last updated:

## Skill Identity

| Field | Value |
|-------|-------|
| Skill name | |
| Source URL | |
| Publisher / maintainer | |
| License / terms | |
| Version / tag / commit SHA | |
| Artifact hash | |
| Install scope | project-local / global |
| Intended agent(s) | Codex / Claude Code / Cursor / Gemini / other |
| Update policy | manual review required / auto-update forbidden / other |

## Purpose and Skill Card

- One-sentence behavior:
- Intended users/workflows:
- Output type and format:
- Known risks:
- Mitigations:
- Skill card path or URL:

## Capability Declaration

| Capability | Used? | Scope | Justification |
|------------|-------|-------|---------------|
| Shell execution | yes/no | | |
| Network egress | yes/no | | |
| File read | yes/no | | |
| File write | yes/no | | |
| Environment / secrets | yes/no | | |
| MCP tools / external tools | yes/no | | |
| Dependency installation | yes/no | | |
| Persistent state / cron / startup | yes/no | | |
| External APIs | yes/no | | |

## Scan Evidence

| Check | Result | Evidence |
|-------|--------|----------|
| SkillSpector static scan | pass/fail/not run | |
| SkillSpector semantic scan | pass/fail/not run/n/a | |
| SARIF report | present/missing/n/a | |
| Dependency vulnerability check | pass/fail/not run | |
| Manual code review | pass/fail/not run | |

Command used:

```bash
skillspector scan ./skill-name --no-llm --format markdown --output docs/security/skills/skill-name/skillspector-report.md
```

## Findings Triage

- Critical/high risk acceptance: no

| Finding | Severity | Decision | Owner | Mitigation / Risk Acceptance |
|---------|----------|----------|-------|------------------------------|
| | | fixed / accepted / rejected | | |

Rules:

- CRITICAL/HIGH findings block install unless fixed or formally accepted.
- Hidden instructions, tool poisoning, credential harvesting, or description-
  behavior mismatch require removal or explicit rejection/acceptance.

## Signature / Integrity

| Check | Result | Evidence |
|-------|--------|----------|
| `skill.oms.sig` present | yes/no | |
| Signature verified | pass/fail/n/a | |
| Certificate / trust anchor | | |
| Unsigned files allowed | no / yes with reason | |
| Commit/hash pinned | yes/no | |

Verification command:

```bash
model_signing verify certificate SKILL_DIR \
  --signature SKILL_DIR/skill.oms.sig \
  --certificate-chain nv-agent-root-cert.pem
```

## Architecture Impact

- New capability profile required: none / Tool-Use / Agentic / Compliance / other
- Runtime tier impact: none / T1 / T2 / T3
- Tool Catalog update required: yes/no
- Contract update required: yes/no
- Cost budget impact: yes/no
- Tasks required:

## Approval Decision

- Decision: approved / rejected / deferred
- Approved install scope:
- Conditions:
- Reviewer:
- Date:
- Re-review trigger:

Re-review triggers include new version, changed source, changed dependency,
changed permission, changed trigger, changed executable file, or local
modification after signature/hash verification.
