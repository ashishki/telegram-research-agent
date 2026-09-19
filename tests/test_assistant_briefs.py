from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from prm.application import PersonalResearchAssistant
from prm.briefs import (
    BriefBuildRequest,
    BriefDocumentStore,
    BriefWindow,
    CoverageSource,
    build_brief_document,
    render_brief,
    render_brief_document,
)
from prm.contracts import OperatorRequest
from prm.conversation import ConversationStore


def _window(*, start: str = "2026-10-25T00:00:00+02:00", end: str = "2026-10-26T00:00:00+01:00") -> BriefWindow:
    return BriefWindow.from_iso(
        timezone_name="Europe/Berlin",
        start_at=start,
        end_at=end,
        generated_at="2026-10-26T01:15:00+01:00",
    )


def _evidence(
    identifier: str,
    source: str,
    *,
    title: str,
    summary: str,
    posted_at: str = "2026-10-25T10:00:00+02:00",
    topics: tuple[str, ...] = ("AI",),
    importance: str = "high",
    urgent: bool = False,
    conflict_group: str | None = None,
    conflict_value: str | None = None,
    repost_family_id: str | None = None,
    project_refs: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "local_archive_provenance": True,
        "evidence_id": identifier,
        "source_url": source,
        "title": title,
        "support_span": summary,
        "posted_at": posted_at,
        "topics": topics,
        "importance": importance,
        "urgent": urgent,
        "conflict_group": conflict_group,
        "conflict_value": conflict_value,
        "repost_family_id": repost_family_id,
        "project_refs": project_refs,
        "project_binding_provenance": "source" if project_refs else "",
    }


def test_brief_document_is_versioned_inspectable_and_dst_half_open() -> None:
    window = _window()
    request = BriefBuildRequest(
        topic="AI updates",
        window=window,
        coverage=(
            CoverageSource("telegram:archive", "checked"),
            CoverageSource("telegram:channel-missing", "unavailable", "not supplied"),
        ),
        evidence=(
            _evidence("dup-low", "https://t.me/example/repost-a", title="Duplicate older", summary="Older duplicate.", importance="low", repost_family_id="origin:eval-release"),
            _evidence("dup-high", "https://t.me/example/repost-b", title="Duplicate selected", summary="Selected duplicate.", importance="high", repost_family_id="origin:eval-release"),
            _evidence("conflict-a", "https://t.me/example/a", title="Deadline source A", summary="Deadline says Monday.", urgent=True, conflict_group="deadline", conflict_value="Monday"),
            _evidence("conflict-b", "https://t.me/example/b", title="Deadline source B", summary="Deadline says Tuesday.", urgent=True, conflict_group="deadline", conflict_value="Tuesday"),
            # The right edge is excluded even across the Europe/Berlin DST
            # shift. It cannot become a fabricated in-week event.
            _evidence("right-edge", "https://t.me/example/end", title="At end", summary="Must be outside.", posted_at="2026-10-26T00:00:00+01:00"),
        ),
    )

    first = build_brief_document(request)
    updated = build_brief_document(
        BriefBuildRequest(
            topic="AI updates",
            window=window,
            coverage=request.coverage,
            evidence=request.evidence,
            previous_document=first,
        )
    )

    assert first.status == "partial"
    assert updated.version == 2
    assert updated.previous_version == first.version_ref
    inspection = first.inspect()
    assert inspection["period"]["interval"] == "[start_at,end_at)"
    assert inspection["coverage"]["complete"] is False
    assert inspection["deduplication"][0]["kept_evidence_ref"] == "evidence_dup-high"
    assert inspection["deduplication"][0]["key"] == "origin:eval-release"
    assert inspection["conflicts"] == [{
        "group": "deadline",
        "evidence_refs": ["evidence_conflict-a", "evidence_conflict-b"],
        "values": ["Monday", "Tuesday"],
    }]
    priorities = {item["item_id"]: (item["importance"], item["urgency"]) for item in inspection["importance_vs_urgency"]}
    assert priorities["brief_item_evidence_conflict-a"] == ("high", "urgent")
    assert "outside_window_evidence_excluded" in inspection["coverage"]["limitations"]
    assert first.to_dict()["schema_version"] == "assistant.brief_document.v1"


def test_brief_views_are_source_backed_and_empty_claim_depends_on_coverage() -> None:
    window = _window(start="2026-09-14T00:00:00+02:00", end="2026-09-21T00:00:00+02:00")
    complete_empty = build_brief_document(
        BriefBuildRequest(
            topic="AI", window=window, evidence=(), coverage=(CoverageSource("telegram:archive", "checked"),),
        )
    )
    partial_empty = build_brief_document(BriefBuildRequest(topic="AI", window=window, evidence=()))
    populated = build_brief_document(
        BriefBuildRequest(
            topic="AI", window=window, coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_evidence(
                "one", "https://t.me/example/1", title="One", summary="One source-backed finding.",
                posted_at="2026-09-16T10:00:00+02:00",
            ),),
        )
    )

    assert "важных изменений не найдено" in render_brief_document(complete_empty).casefold()
    partial_text = render_brief_document(partial_empty).casefold()
    assert "не вывод за весь период" in partial_text
    assert "важных изменений не найдено" not in partial_text
    rendered = render_brief_document(populated)
    assert "https://t.me/example/1" in rendered
    assert "важность: high; срочность" in rendered
    assert len(rendered) <= 2400


def test_invalid_or_unselected_local_evidence_cannot_become_a_brief_source() -> None:
    document = build_brief_document(
        BriefBuildRequest(
            topic="AI",
            window=_window(),
            evidence=({
                "evidence_id": "external",
                "source_url": "https://example.test/not-local",
                "support_span": "Untrusted external input.",
                "posted_at": "2026-10-25T10:00:00+02:00",
            },),
        )
    )

    assert document.status == "partial"
    assert document.evidence == ()
    assert "invalid_local_evidence_excluded" in document.inspect()["coverage"]["limitations"]


def test_exact_ephemeral_render_lookup_has_no_latest_fallback() -> None:
    document = build_brief_document(
        BriefBuildRequest(
            topic="AI", window=_window(), coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_evidence("one", "https://t.me/example/1", title="One", summary="Detail."),),
        )
    )
    store = BriefDocumentStore()
    conversation_id = "conversation_" + "a" * 24
    store.bind_visible(
        conversation_id=conversation_id,
        response_ref="response_" + "b" * 24,
        document=document,
    )

    assert render_brief(document.brief_id, document.version, "short", conversation_id=conversation_id, store=store)
    assert render_brief(document.brief_id, document.version + 1, "short", conversation_id=conversation_id, store=store) is None
    assert render_brief(document.brief_id, document.version, "short", store=store) is None
    assert render_brief(
        document.brief_id, document.version, "short", conversation_id="conversation_" + "c" * 24, store=store,
    ) is None
    store.forget_conversation(conversation_id)
    assert render_brief(document.brief_id, document.version, "telegram", conversation_id=conversation_id, store=store) is None


def test_brief_mode_projects_current_selected_archive_evidence_without_a_provider(monkeypatch) -> None:
    observed = datetime.now(timezone.utc).isoformat()
    payload = {
        "status": "ok",
        "direct_answer": "Archive result.",
        "answer_gate": {"allow_answer": True, "external_verification_required": False, "current_claim_allowed": True},
        "archive_evidence": {"items": [{
            "archive_document_id": "tg:brief", "source_url": "https://t.me/example/brief",
            "snippet": "A local archive selection for the brief.", "posted_at": observed,
            "title": "Local brief source", "topics": ["AI"], "importance": "high",
        }]},
        "evidence_quality": {"items": [{
            "evidence_id": "tg:brief", "source_url": "https://t.me/example/brief",
            "support_span": "A local archive selection for the brief.", "relevance_label": "direct",
        }]},
        "professional_answer": {}, "project_fit": {}, "project_decision": {}, "claim_ledger": {},
        "unknowns": [], "next_steps": {}, "receipt": {}, "privacy": {},
    }
    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: payload)
    monkeypatch.setattr("prm.application.build_research_facade", lambda **kwargs: SimpleNamespace())
    assistant = PersonalResearchAssistant(
        settings=SimpleNamespace(db_path=":memory:"),
        conversations=ConversationStore(),
        briefs=BriefDocumentStore(),
    )

    result = assistant.answer(OperatorRequest(query="AI за неделю", mode="brief", chat_id="42"))

    assert result.mode == "brief"
    assert result.payload["brief_document_created"] is True
    assert result.payload["retrieval_performed"] is True
    assert result.payload["brief_document"]["evidence_refs"] == ["evidence_tg_brief"]


def test_active_brief_window_parses_explicit_range_and_selected_timezone() -> None:
    from prm.briefs import parse_requested_brief_window

    window, basis = parse_requested_brief_window(
        "бриф AI с 2026-10-25 по 2026-10-26 timezone Europe/Berlin",
        now=datetime(2026, 10, 30, tzinfo=timezone.utc),
    )

    assert basis == "explicit_requested_range"
    assert window.timezone == "Europe/Berlin"
    assert window.to_dict()["start_at"] == "2026-10-24T22:00:00Z"
    assert window.to_dict()["end_at"] == "2026-10-25T23:00:00Z"


def test_project_section_needs_a_source_binding_and_history_needs_same_owner() -> None:
    request = BriefBuildRequest(
        topic="AI",
        window=_window(),
        owner_ref="owner_primary",
        coverage=(CoverageSource("telegram:archive", "checked"),),
        evidence=(_evidence(
            "project", "https://t.me/example/project", title="Project signal", summary="Source connects this signal to the project.",
            project_refs=("telegram-research-agent",),
        ),),
    )
    document = build_brief_document(request)
    section = document.sections[0]
    assert section.section_id == "for_projects"
    assert section.items[0].project_refs == ("telegram-research-agent",)
    assert document.inspect()["importance_vs_urgency"][0]["project_refs"] == ["telegram-research-agent"]

    other_owner = build_brief_document(
        BriefBuildRequest(
            topic="AI", window=_window(), owner_ref="owner_other",
            coverage=(CoverageSource("telegram:archive", "checked"),), evidence=(),
        )
    )
    with pytest.raises(ValueError, match="one owner scope"):
        BriefBuildRequest(
            topic="AI", window=_window(), owner_ref="owner_primary", evidence=(), comparison_document=other_owner,
        )


def test_fresh_content_has_distinct_identity_and_mobile_card_has_full_navigation() -> None:
    window = _window()
    first = build_brief_document(
        BriefBuildRequest(
            topic="AI", window=window, owner_ref="owner_primary", coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_evidence("one", "https://t.me/example/one", title="One", summary="First selected source."),),
        )
    )
    second = build_brief_document(
        BriefBuildRequest(
            topic="AI", window=window, owner_ref="owner_primary", coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_evidence("two", "https://t.me/example/two", title="Two", summary="Different selected source."),),
        )
    )
    many = build_brief_document(
        BriefBuildRequest(
            topic="AI", window=window, owner_ref="owner_primary", coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=tuple(
                _evidence(
                    f"many-{index}", f"https://t.me/example/many-{index}", title=f"Item {index}",
                    summary=f"Bounded local detail {index}.", importance="medium",
                )
                for index in range(1, 6)
            ),
        )
    )

    assert first.version_ref != second.version_ref
    assert first.inspect()["brief_ref"]["content_digest"] != second.inspect()["brief_ref"]["content_digest"]
    card = render_brief_document(many)
    full = render_brief_document(many, view="full")
    assert "покажи полный бриф" in card
    assert "Item 5" not in card
    assert "Item 5" in full
    assert "…" not in full
