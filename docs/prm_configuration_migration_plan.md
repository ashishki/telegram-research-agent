# PRM Configuration Migration Plan

Status: proposed; no profile or project configuration is changed here.

Propose, then obtain exact approval for: default `ai_systems_engineer` and `portfolio_builder` lenses; a Project Portfolio V2 descriptor with status, priority, goal, blocker, next proof, capabilities, signal preferences, reviewed/owner/source metadata and aliases; and default candidate projects `telegram-research-agent` and `AI_workflow_playbook`. Preserve legacy descriptions in compatibility metadata. Inspect Agent-Runtime-Grid and Eval-Ground-Truth-Lab before classifying them; do not infer an unavailable repository is inactive.

Propose archive refresh every 6–24 hours, reaction sync as an independent failure domain, and incremental/bounded vector maintenance. Schedule, timezone, rate limits, persistent proposal/receipt schema, raw-question retention, provider budget/egress, live fetch/trust and four-week validation all require approval.

Migration sequence: redacted config diff, fixture validation, local backup, exact approval, write, read-only validation, retained prior configuration. Compatibility maps old project keywords. Rollback restores old config and disables only the new resolver; it never deletes saved objects or canonical archive rows. Failed validation leaves current config untouched.
