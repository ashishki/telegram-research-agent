"""Active Personal Research Memory application boundary."""

from typing import TYPE_CHECKING, Any

from .contracts import AssistantResult, OperatorRequest

if TYPE_CHECKING:
    from .application import PersonalResearchAssistant

__all__ = ["AssistantResult", "OperatorRequest", "PersonalResearchAssistant"]


def __getattr__(name: str) -> Any:
    """Avoid importing the application while a PRM submodule is loading.

    `assistant.memory_research` imports `prm.research_planner`; eagerly loading
    the application here would import `assistant.memory_research` back before
    its public symbols are defined. Keep the package-level compatibility export
    but resolve it only when somebody explicitly asks for it.
    """

    if name == "PersonalResearchAssistant":
        from .application import PersonalResearchAssistant

        return PersonalResearchAssistant
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
