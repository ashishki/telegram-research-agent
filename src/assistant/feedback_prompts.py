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
      "feedback_type": "read|useful|tried|applied_to_project|too_shallow|too_long|confusing_visual|missing_visual|duplicate_content|action_completed|radar_decision_useful|reaction_effect_missing|source_trust_correction|desired_report_change|missed_important_post|no_missed_posts|wrong_priority|not_interested|noise|trust_too_high|trust_too_low|verify_first|correction|retraction|accidental_feedback",
      "target_type": "report|report_section|idea_thread|knowledge_atom|source_channel|read_queue|experiment|action|missed_post|trust_correction|feedback_event|operator_context",
      "target_ref": "optional stable reference",
      "report_surface": "weekly_brief|knowledge_atlas|mvp_radar|reaction_personalization|project_action|visual|audit_explorer|report_package",
      "section_id": "stable report section id, never unknown",
      "item_ref": "stable report item id, never unknown",
      "feedback_classification": "useful|wrong_priority|too_shallow|too_long|confusing_visual|missing_visual|duplicate_content|action_completed|applied_to_project|radar_decision_useful|reaction_effect_missing|source_trust_correction|desired_report_change",
      "application_status": "applied|unchanged|code_config_required|rejected|pending",
      "application_reason": "why the confirmed event has this application status",
      "originating_report_item_ref": "optional original action/project/report item ref",
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
- Target every memory event to a surface, section, and item. Use weekly_brief,
  knowledge_atlas, mvp_radar, reaction_personalization, project_action, or
  visual when those surfaces are named or implied.
- Classify feedback with the controlled feedback_classification vocabulary.
- Completed actions or project outcomes should use action_completed or
  applied_to_project and preserve the originating report item when present.
- Visual complaints should use confusing_visual or missing_visual.
- Radar decision feedback should use radar_decision_useful.
- Reaction personalization misses should use reaction_effect_missing.
- Missed important source/post feedback should preserve source URLs when present.
- Trust corrections should use trust_too_high, trust_too_low, or verify_first.
- Correction/retraction feedback should target an existing feedback_event and stay append-only.
- Requests to change config, prompts, projects, code, scoring, or profiles are manual suggestions or Codex task drafts, not memory events.
- If feedback asks for direct mutation, add a risk note that manual approval is required.
- Persistent profile, config, prompt, project, scoring, or code changes must be
  application_status=code_config_required unless the operator separately
  confirms that mutation outside this feedback draft.

Week label: {clean_week}
Input kind: {input_kind}
Operator feedback:
{text}
""".strip()
