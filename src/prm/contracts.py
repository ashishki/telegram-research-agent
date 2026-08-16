"""Typed contracts shared by Telegram, CLI and evaluation interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

RequestMode = Literal["auto", "research", "brief", "chat"]
ResponseMode = Literal["research", "brief", "chat", "project_clarify", "clarify"]
PrimaryIntent = Literal[
    "archive_lookup",
    "archive_synthesis",
    "archive_to_action",
    "project_mapping",
    "decision_support",
    "current_fact_verification",
    "memory_action",
    "writer_brief",
    "freeform_chat",
]
ResponseContractId = Literal[
    "archive_lookup.v2",
    "archive_research.v2",
    "project_mapping.v2",
    "decision_support.v2",
    "current_fact.v2",
    "brief.v1",
    "chat.v1",
]


@dataclass(frozen=True, slots=True)
class OperatorRequest:
    query: str
    mode: RequestMode = "auto"
    chat_id: str = "local-cli"
    input_kind: Literal["text", "voice_transcript"] = "text"
    project_name: str = ""
    remember_dialog: bool = False


@dataclass(frozen=True, slots=True)
class AssistantResult:
    interaction_id: str
    status: str
    mode: ResponseMode
    text: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    operator_context: Mapping[str, Any] = field(default_factory=dict)
    final_answer_verification: Mapping[str, Any] = field(default_factory=dict)
    route: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "interaction_id": self.interaction_id,
            "status": self.status,
            "mode": self.mode,
            "text": self.text,
            # Compatibility alias used by the private UX harness.
            "final_answer": self.text,
            "payload": dict(self.payload),
            "operator_context": dict(self.operator_context),
            "final_answer_verification": dict(self.final_answer_verification),
            "route": dict(self.route),
        }
