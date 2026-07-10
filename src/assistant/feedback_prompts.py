FEEDBACK_STRATEGIST_SYSTEM_PROMPT = """
You are the private feedback strategist for a single-operator AI intelligence workflow.
Interpret feedback as a private learning signal for future weekly workbooks.

Rules:
- Propose memory events only; never claim memory has been written.
- Separate memory events from report/workbook change suggestions.
- Separate Codex task drafts from memory events.
- Never apply or imply code, config, profile, project, scoring, or prompt changes.
- No reaction or silence is unknown, not negative feedback.
- Use explicit uncertainty when the operator feedback is ambiguous.
- Return JSON only.
""".strip()


def build_feedback_strategist_prompt(*, week_label: str | None, input_kind: str, text: str) -> str:
    clean_week = week_label or "unknown"
    return f"""
Interpret this operator feedback for the AI Intelligence Workbook.

Return JSON with exactly these top-level keys:
{{
  "memory_events_proposed": [
    {{
      "feedback_type": "read|useful|tried|applied_to_project|too_shallow|missed_important_post|no_missed_posts|wrong_priority|not_interested|noise|trust_too_high|trust_too_low|verify_first|correction|retraction|accidental_feedback",
      "target_type": "report|report_section|idea_thread|knowledge_atom|source_channel|read_queue|experiment|action|missed_post|trust_correction|feedback_event|operator_context",
      "target_ref": "optional stable reference",
      "source_url": "optional URL",
      "notes": "operator-grounded note"
    }}
  ],
  "report_changes_suggested": [
    {{"text": "manual report/workbook change suggestion", "target_ref": "optional"}}
  ],
  "codex_tasks_suggested": [
    {{
      "title": "manual Codex task draft",
      "why": "why this might matter",
      "likely_files": ["optional file paths"],
      "acceptance": ["optional acceptance criteria"],
      "verification": ["optional verification commands"]
    }}
  ],
  "clarifying_questions": ["question only when ambiguity blocks correct memory"],
  "risk_notes": ["risks such as ambiguous feedback or unsafe mutation requests"],
  "confirmation_summary": "short operator-facing summary of what is proposed"
}}

Extraction guidance:
- Useful/helpful/read/tried/applied feedback should become positive memory events.
- Wrong priority, not interesting, noisy, or too shallow feedback should become calibration memory events.
- Missed important source/post feedback should preserve source URLs when present.
- Trust corrections should use trust_too_high, trust_too_low, or verify_first.
- Correction/retraction feedback should target an existing feedback_event and stay append-only.
- Requests to change config, prompts, projects, code, scoring, or profiles are manual suggestions or Codex task drafts, not memory events.
- If feedback asks for direct mutation, add a risk note that manual approval is required.

Week label: {clean_week}
Input kind: {input_kind}
Operator feedback:
{text}
""".strip()
