from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

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
            _evidence("dup-low", "https://t.me/example/dup", title="Duplicate older", summary="Older duplicate.", importance="low"),
            _evidence("dup-high", "https://t.me/example/dup", title="Duplicate selected", summary="Selected duplicate.", importance="high"),
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
    store.bind_visible(
        conversation_id="conversation_" + "a" * 24,
        response_ref="response_" + "b" * 24,
        document=document,
    )

    assert render_brief(document.brief_id, document.version, "short", store=store)
    assert render_brief(document.brief_id, document.version + 1, "short", store=store) is None
    store.forget_conversation("conversation_" + "a" * 24)
    assert render_brief(document.brief_id, document.version, "telegram", store=store) is None


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
    assert result.payload["retrieval_performed"] is False
    assert result.payload["brief_document"]["evidence_refs"] == ["evidence_tg_brief"]
