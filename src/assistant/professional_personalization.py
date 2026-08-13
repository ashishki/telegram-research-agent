"""Non-mutating professional lens contracts for PRM-UX-3."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


PROFESSIONAL_PERSONALIZATION_SCHEMA_VERSION = "professional_personalization.v2"
LENS_IDS = (
    "ai_systems_engineer",
    "portfolio_builder",
    "career",
    "product_strategy",
    "enterprise_ai_adoption",
    "writer_editor",
    "learning",
)

_LENS_DEFINITIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "ai_systems_engineer": {
        "goals": ("agent reliability", "evaluation", "RAG quality", "runtime safety"),
        "evidence_preferences": ("official documentation", "code", "benchmarks", "postmortems"),
        "output_preferences": ("architecture pattern", "failure mode", "eval case", "risk boundary"),
    },
    "portfolio_builder": {
        "goals": ("stronger repositories", "visible proof", "PR-sized improvement"),
        "evidence_preferences": ("repository docs", "tests", "receipts", "implementation patterns"),
        "output_preferences": ("repo implication", "PR-sized change", "acceptance criteria", "portfolio narrative"),
    },
    "career": {
        "goals": ("AI engineer readiness", "portfolio evidence", "market skill signals"),
        "evidence_preferences": ("verified market sources", "archive signals", "portfolio evidence"),
        "output_preferences": ("recurring requirement", "missing proof", "next career action"),
    },
    "product_strategy": {
        "goals": ("AI adoption pain", "workflow opportunities", "demand evidence"),
        "evidence_preferences": ("user pain", "independent cases", "manual workarounds", "measurable effect"),
        "output_preferences": ("problem pattern", "evidence maturity", "validation step", "do-not-build boundary"),
    },
    "enterprise_ai_adoption": {
        "goals": ("operating-model change", "guardrails", "measurable rollout"),
        "evidence_preferences": ("enterprise cases", "postmortems", "implementation details", "adoption metrics"),
        "output_preferences": ("enterprise case", "failure mode", "adoption metric", "project implication"),
    },
    "writer_editor": {
        "goals": ("source-backed Russian posts", "strong thesis", "practical takeaway"),
        "evidence_preferences": ("Telegram signals", "primary sources", "clear cases", "source links"),
        "output_preferences": ("editor brief", "evidence packet", "story angle", "verification needs"),
    },
    "learning": {
        "goals": ("understand difficult ideas", "small experiment", "retained explanation"),
        "evidence_preferences": ("definitions", "examples", "project context", "runnable experiments"),
        "output_preferences": ("plain explanation", "analogy", "experiment", "success criterion"),
    },
}


def professional_lens_schema() -> dict[str, Any]:
    """Return immutable-by-convention schema data; this never reads or writes profiles."""

    return {
        "schema_version": PROFESSIONAL_PERSONALIZATION_SCHEMA_VERSION,
        "lens_policy": {
            "recall_never_reduced_by_lens": True,
            "durable_changes_require_confirmation": True,
        },
        "professional_lenses": {lens_id: dict(definition) for lens_id, definition in _LENS_DEFINITIONS.items()},
    }


def normalize_lens_id(value: object) -> str | None:
    lens_id = str(value or "").strip().casefold()
    return lens_id if lens_id in _LENS_DEFINITIONS else None


def rerank_for_professional_lens(
    candidates: Sequence[Mapping[str, Any]], *, lens_id: str | None
) -> list[dict[str, Any]]:
    """Softly reorder candidates without filtering the broad retrieval set."""

    normalized_lens = normalize_lens_id(lens_id)
    preferences = _LENS_DEFINITIONS.get(normalized_lens or "", {})
    terms = " ".join(
        item for field in ("goals", "evidence_preferences", "output_preferences") for item in preferences.get(field, ())
    ).casefold()
    ranked: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        item = dict(candidate)
        evidence = " ".join(str(item.get(key) or "") for key in ("title", "snippet", "content", "channel_username")).casefold()
        matches = sum(1 for term in terms.split() if len(term) > 3 and term in evidence)
        item["professional_lens"] = normalized_lens or "neutral"
        item["professional_lens_soft_boost"] = matches
        item["_original_index"] = index
        ranked.append(item)
    ranked.sort(
        key=lambda item: (-int(item["professional_lens_soft_boost"]), int(item["_original_index"])),
    )
    for item in ranked:
        item.pop("_original_index", None)
    return ranked


def propose_lens_preference_change(*, requested_lens: str, current_default_lens: str | None = None) -> dict[str, Any]:
    """Represent a permanent preference request without applying any configuration write."""

    normalized_lens = normalize_lens_id(requested_lens)
    return {
        "schema_version": "professional_lens_preference_proposal.v1",
        "status": "proposed" if normalized_lens else "invalid",
        "requested_lens": normalized_lens,
        "current_default_lens": normalize_lens_id(current_default_lens),
        "requires_human_confirmation": True,
        "write_performed": False,
        "profile_mutation_exposed": False,
        "message": (
            "Подтверди смену постоянной профессиональной линзы перед изменением профиля."
            if normalized_lens
            else "Неизвестная профессиональная линза; профиль не изменён."
        ),
    }
