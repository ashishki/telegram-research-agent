from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from types import SimpleNamespace

import pytest

from prm.application import PersonalResearchAssistant
from prm.briefs import (
    BriefBuildRequest,
    BriefDocumentStore,
    BriefWindow,
    CoverageSource,
    brief_owner_ref_from_authenticated_private_tuple,
    build_brief_document,
    rebuild_brief_request,
    render_brief,
    render_brief_document,
)
from prm.contracts import OperatorRequest
from prm.conversation import ConversationStore
from prm.research_facade import BriefWindowResearchFacade
from db.migrate import run_migrations


def _window(*, start: str = "2026-10-25T00:00:00+02:00", end: str = "2026-10-26T00:00:00+01:00") -> BriefWindow:
    return BriefWindow.from_iso(
        timezone_name="Europe/Berlin",
        start_at=start,
        end_at=end,
        generated_at="2026-10-26T01:15:00+01:00",
    )


def _owner_tuple(identifier: str) -> tuple[str, str, str]:
    return identifier, identifier, identifier


def _owner_ref(identifier: str) -> str:
    owner_ref = brief_owner_ref_from_authenticated_private_tuple(*_owner_tuple(identifier))
    assert owner_ref is not None
    return owner_ref


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
    **temporal_metadata: object,
) -> dict[str, object]:
    evidence: dict[str, object] = {
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
    evidence.update(temporal_metadata)
    return evidence


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
    assert "<b>Короткий бриф</b>" in rendered
    assert '<a href="https://t.me/example/1">Открыть источник</a>' in rendered
    assert "Важность: важно · Срочность: без срока" in rendered
    assert "Версия:" not in rendered
    assert len(rendered) <= 2400


def test_telegram_card_is_compact_html_and_escapes_archive_derived_content() -> None:
    document = build_brief_document(
        BriefBuildRequest(
            topic="AI <weekly>",
            window=_window(),
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(
                _evidence(
                    "html",
                    "https://t.me/example/html?one=1&two=2",
                    title="<b>Not markup</b>",
                    summary="Archive says <tag> & keeps the characters visible.",
                ),
            ),
        )
    )

    rendered = render_brief_document(document)

    assert "<b>Короткий бриф</b>" in rendered
    assert "&lt;weekly&gt;" in rendered
    assert "&lt;b&gt;Not markup&lt;/b&gt;" in rendered
    assert "&lt;tag&gt; &amp; keeps the characters visible." in rendered
    assert 'href="https://t.me/example/html?one=1&amp;two=2"' in rendered
    assert "Покрытие: проверено" in rendered
    assert "Версия:" not in rendered
    assert len(rendered) <= 2400


def test_expanded_telegram_brief_uses_user_language_not_internal_audit_fields() -> None:
    document = build_brief_document(
        BriefBuildRequest(
            topic="AI за неделю",
            window=_window(),
            coverage=(CoverageSource("telegram:archive", "partial", "bounded selection"),),
            evidence=(
                _evidence(
                    "unranked-one", "https://t.me/example/unranked-one", title="Unranked one",
                    summary="A local archive excerpt.", importance="unknown", urgent=None,
                ),
                _evidence(
                    "unranked-two", "https://t.me/example/unranked-two", title="Unranked two",
                    summary="Another local archive excerpt.", importance="unknown", urgent=None,
                ),
            ),
        )
    )

    rendered = render_brief_document(document, view="full")

    assert rendered.startswith("🗞 <b>Подробный бриф</b>")
    assert "Это подборка по теме, а не рейтинг важности." in rendered
    assert "Важность: не отмечена · Срочность: срок не указан" in rendered
    assert '<a href="https://t.me/example/unranked-one">Открыть источник</a>' in rendered
    assert "снимок sha256" not in rendered
    assert document.brief_id not in rendered


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


def test_exact_owner_scoped_brief_history_survives_a_store_restart_and_can_be_forgotten(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "assistant-briefs.db"
    monkeypatch.setenv("AGENT_DB_PATH", str(db_path))
    assert run_migrations() == db_path
    primary_tuple = _owner_tuple("42")
    primary_owner_ref = _owner_ref("42")
    secondary_tuple = _owner_tuple("43")
    secondary_owner_ref = _owner_ref("43")
    first = build_brief_document(
        BriefBuildRequest(
            topic="AI", window=_window(), owner_ref=primary_owner_ref,
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_evidence("one", "https://t.me/example/one", title="One", summary="Persisted bounded source."),),
        )
    )
    second = build_brief_document(
        BriefBuildRequest(
            topic="AI", window=_window(), owner_ref=primary_owner_ref,
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_evidence("two", "https://t.me/example/two", title="Two", summary="A revised exact source."),),
            previous_document=first,
        )
    )
    other = build_brief_document(
        BriefBuildRequest(
            topic="AI", window=_window(), owner_ref=secondary_owner_ref,
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_evidence("other", "https://t.me/example/other", title="Other", summary="Separate owner source."),),
        )
    )
    initial = BriefDocumentStore(db_path=str(db_path))
    initial.bind_visible(
        conversation_id="conversation_" + "a" * 24,
        response_ref="response_" + "b" * 24,
        document=first,
        authenticated_chat_id=primary_tuple[0], authenticated_actor_id=primary_tuple[1], authenticated_owner_chat_id=primary_tuple[2],
    )
    initial.bind_visible(
        conversation_id="conversation_" + "a" * 24,
        response_ref="response_" + "c" * 24,
        document=second,
        comparison_document=first,
        authenticated_chat_id=primary_tuple[0], authenticated_actor_id=primary_tuple[1], authenticated_owner_chat_id=primary_tuple[2],
    )
    initial.bind_visible(
        conversation_id="conversation_" + "d" * 24,
        response_ref="response_" + "e" * 24,
        document=other,
        authenticated_chat_id=secondary_tuple[0], authenticated_actor_id=secondary_tuple[1], authenticated_owner_chat_id=secondary_tuple[2],
    )

    restarted = BriefDocumentStore(db_path=str(db_path))
    assert restarted.resolve_visible(
        conversation_id="conversation_" + "a" * 24,
        response_ref="response_" + "c" * 24,
    ) is None
    assert restarted.get_persisted_document(
        authenticated_chat_id=primary_tuple[0], authenticated_actor_id=primary_tuple[1], authenticated_owner_chat_id=primary_tuple[2], brief_id=first.brief_id, version=1,
    ) == first
    assert restarted.get_persisted_document(
        authenticated_chat_id=primary_tuple[0], authenticated_actor_id=primary_tuple[1], authenticated_owner_chat_id=primary_tuple[2], brief_id=second.brief_id, version=2,
    ) == second
    assert restarted.get_persisted_document(
        authenticated_chat_id=secondary_tuple[0], authenticated_actor_id=secondary_tuple[1], authenticated_owner_chat_id=secondary_tuple[2], brief_id=first.brief_id, version=1,
    ) is None
    assert restarted.list_persisted_versions(
        authenticated_chat_id=primary_tuple[0], authenticated_actor_id=primary_tuple[1], authenticated_owner_chat_id=primary_tuple[2], brief_id=first.brief_id,
    ) == (
        first.version_ref,
        second.version_ref,
    )
    assert render_brief(
        first.brief_id, 1, "full", authenticated_chat_id=primary_tuple[0], authenticated_actor_id=primary_tuple[1], authenticated_owner_chat_id=primary_tuple[2], store=restarted,
    ) == render_brief_document(first, view="full")
    assert render_brief(first.brief_id, 1, "full", store=restarted) is None

    forged_tuple = _owner_tuple("44")
    assert restarted.get_persisted_document(
        authenticated_chat_id=forged_tuple[0], authenticated_actor_id=forged_tuple[1], authenticated_owner_chat_id=forged_tuple[2], brief_id=first.brief_id, version=1,
    ) is None
    assert restarted.list_persisted_versions(
        authenticated_chat_id=forged_tuple[0], authenticated_actor_id=forged_tuple[1], authenticated_owner_chat_id=forged_tuple[2], brief_id=first.brief_id,
    ) == ()
    with pytest.raises(ValueError, match="durable ownership"):
        initial.bind_visible(
            conversation_id="conversation_" + "f" * 24,
            response_ref="response_" + "f" * 24,
            document=first,
            authenticated_chat_id=forged_tuple[0],
            authenticated_actor_id=forged_tuple[1],
            authenticated_owner_chat_id=forged_tuple[2],
        )
    restarted.forget_owner(
        authenticated_chat_id=forged_tuple[0], authenticated_actor_id=forged_tuple[1], authenticated_owner_chat_id=forged_tuple[2],
    )
    assert restarted.get_persisted_document(
        authenticated_chat_id=primary_tuple[0], authenticated_actor_id=primary_tuple[1], authenticated_owner_chat_id=primary_tuple[2], brief_id=first.brief_id, version=1,
    ) == first

    integer_tuple = (42, 42, 42)
    integer_document = build_brief_document(
        BriefBuildRequest(
            topic="AI integer", window=_window(), owner_ref=primary_owner_ref,
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_evidence("integer", "https://t.me/example/integer", title="Integer", summary="Must remain visible-only."),),
        )
    )
    initial.bind_visible(
        conversation_id="conversation_integer",
        response_ref="response_" + "1" * 24,
        document=integer_document,
        authenticated_chat_id=integer_tuple[0],
        authenticated_actor_id=integer_tuple[1],
        authenticated_owner_chat_id=integer_tuple[2],
    )
    assert restarted.get_persisted_document(
        authenticated_chat_id=integer_tuple[0], authenticated_actor_id=integer_tuple[1], authenticated_owner_chat_id=integer_tuple[2], brief_id=first.brief_id, version=1,
    ) is None
    assert restarted.list_persisted_versions(
        authenticated_chat_id=integer_tuple[0], authenticated_actor_id=integer_tuple[1], authenticated_owner_chat_id=integer_tuple[2], brief_id=first.brief_id,
    ) == ()
    assert restarted.get_persisted_document(
        authenticated_chat_id=primary_tuple[0], authenticated_actor_id=primary_tuple[1], authenticated_owner_chat_id=primary_tuple[2], brief_id=integer_document.brief_id, version=1,
    ) is None
    restarted.forget_owner(
        authenticated_chat_id=integer_tuple[0], authenticated_actor_id=integer_tuple[1], authenticated_owner_chat_id=integer_tuple[2],
    )
    assert restarted.get_persisted_document(
        authenticated_chat_id=primary_tuple[0], authenticated_actor_id=primary_tuple[1], authenticated_owner_chat_id=primary_tuple[2], brief_id=first.brief_id, version=1,
    ) == first

    restarted.forget_owner(
        authenticated_chat_id=primary_tuple[0], authenticated_actor_id=primary_tuple[1], authenticated_owner_chat_id=primary_tuple[2],
    )
    assert restarted.get_persisted_document(
        authenticated_chat_id=primary_tuple[0], authenticated_actor_id=primary_tuple[1], authenticated_owner_chat_id=primary_tuple[2], brief_id=first.brief_id, version=1,
    ) is None
    assert restarted.get_persisted_document(
        authenticated_chat_id=secondary_tuple[0], authenticated_actor_id=secondary_tuple[1], authenticated_owner_chat_id=secondary_tuple[2], brief_id=other.brief_id, version=1,
    ) == other


def test_persisted_brief_history_fails_closed_if_its_json_is_altered(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "tampered-brief.db"
    monkeypatch.setenv("AGENT_DB_PATH", str(db_path))
    run_migrations()
    primary_tuple = _owner_tuple("42")
    primary_owner_ref = _owner_ref("42")
    document = build_brief_document(
        BriefBuildRequest(
            topic="AI", window=_window(), owner_ref=primary_owner_ref,
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_evidence("one", "https://t.me/example/one", title="One", summary="Bounded local source."),),
        )
    )
    store = BriefDocumentStore(db_path=str(db_path))
    store.bind_visible(
        conversation_id="conversation_" + "a" * 24,
        response_ref="response_" + "b" * 24,
        document=document,
        authenticated_chat_id=primary_tuple[0], authenticated_actor_id=primary_tuple[1], authenticated_owner_chat_id=primary_tuple[2],
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE assistant_brief_documents SET document_json = ? WHERE owner_ref = ? AND brief_id = ? AND version = ?",
            ('{"schema_version":"prm_brief_document_storage.v1"}', primary_owner_ref, document.brief_id, 1),
        )
    restarted = BriefDocumentStore(db_path=str(db_path))
    assert restarted.get_persisted_document(
        authenticated_chat_id=primary_tuple[0], authenticated_actor_id=primary_tuple[1], authenticated_owner_chat_id=primary_tuple[2], brief_id=document.brief_id, version=1,
    ) is None


def test_persisted_brief_history_rejects_semantic_history_tampering(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "semantic-tamper-brief.db"
    monkeypatch.setenv("AGENT_DB_PATH", str(db_path))
    run_migrations()
    primary_tuple = _owner_tuple("42")
    primary_owner_ref = _owner_ref("42")
    prior = build_brief_document(
        BriefBuildRequest(
            topic="AI", window=_window(), owner_ref=primary_owner_ref,
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_evidence("prior", "https://t.me/example/prior", title="Prior", summary="Prior exact source."),),
        )
    )
    comparison = build_brief_document(
        BriefBuildRequest(
            topic="AI", owner_ref=primary_owner_ref,
            window=_window(start="2026-10-24T00:00:00+02:00", end="2026-10-25T00:00:00+02:00"),
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_evidence(
                "comparison", "https://t.me/example/comparison", title="Comparison", summary="Comparison exact source.",
                posted_at="2026-10-24T10:00:00+02:00",
            ),),
        )
    )
    document = build_brief_document(
        BriefBuildRequest(
            topic="AI", window=_window(), owner_ref=primary_owner_ref,
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_evidence("current", "https://t.me/example/current", title="Current", summary="Current exact source."),),
            previous_document=prior,
            comparison_document=comparison,
        )
    )
    store = BriefDocumentStore(db_path=str(db_path))
    store.bind_visible(
        conversation_id="conversation_" + "a" * 24,
        response_ref="response_" + "b" * 24,
        document=document,
        comparison_document=comparison,
        authenticated_chat_id=primary_tuple[0], authenticated_actor_id=primary_tuple[1], authenticated_owner_chat_id=primary_tuple[2],
    )
    with sqlite3.connect(db_path) as connection:
        original_json = connection.execute(
            "SELECT document_json FROM assistant_brief_documents WHERE owner_ref = ? AND brief_id = ? AND version = ?",
            (primary_owner_ref, document.brief_id, document.version),
        ).fetchone()[0]
        original = json.loads(original_json)
        for field, value in (
            ("previous_version", None),
            ("comparison_ref", None),
            ("selection_reasons", ["local_archive_selected"]),
        ):
            altered = {**original, field: value}
            connection.execute(
                "UPDATE assistant_brief_documents SET document_json = ? WHERE owner_ref = ? AND brief_id = ? AND version = ?",
                (json.dumps(altered, ensure_ascii=False, sort_keys=True), primary_owner_ref, document.brief_id, document.version),
            )
            connection.commit()
            assert BriefDocumentStore(db_path=str(db_path)).get_persisted_document(
                authenticated_chat_id=primary_tuple[0], authenticated_actor_id=primary_tuple[1], authenticated_owner_chat_id=primary_tuple[2],
                brief_id=document.brief_id, version=document.version,
            ) is None


def test_application_default_store_keeps_only_exact_history_after_restart(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "application-briefs.db"
    monkeypatch.setenv("AGENT_DB_PATH", str(db_path))
    run_migrations()
    primary_tuple = _owner_tuple("42")
    primary_owner_ref = _owner_ref("42")
    request = BriefBuildRequest(
        topic="AI", window=_window(), owner_ref="owner_caller_scope",
        coverage=(CoverageSource("telegram:archive", "checked"),),
        evidence=(_evidence("one", "https://t.me/example/one", title="One", summary="Application persistence source."),),
    )
    assistant = PersonalResearchAssistant(
        settings=SimpleNamespace(db_path=str(db_path)),
        conversations=ConversationStore(),
    )
    result = assistant.answer(OperatorRequest(
        query="AI", mode="brief", chat_id="42", actor_id="42", owner_chat_id="42", brief_request=request,
    ))
    document = result.payload["brief_document"]
    conversation_id = result.payload["conversation"]["conversation_id"]
    response_ref = result.payload["conversation"]["response_refs"][0]

    restarted = PersonalResearchAssistant(
        settings=SimpleNamespace(db_path=str(db_path)),
        conversations=ConversationStore(),
    )
    assert restarted.briefs.resolve_visible(conversation_id=conversation_id, response_ref=response_ref) is None
    restored = restarted.briefs.get_persisted_document(
        authenticated_chat_id=primary_tuple[0], authenticated_actor_id=primary_tuple[1], authenticated_owner_chat_id=primary_tuple[2],
        brief_id=str(document["brief_id"]),
        version=int(document["version"]),
    )
    assert restored is not None
    assert restored.to_dict() == document
    assert document["owner_ref"] == primary_owner_ref


def test_durable_brief_history_rejects_group_missing_mismatched_and_cli_identity_tuples(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "unauthenticated-briefs.db"
    monkeypatch.setenv("AGENT_DB_PATH", str(db_path))
    run_migrations()
    request = BriefBuildRequest(
        topic="AI", window=_window(), owner_ref="owner_caller_scope",
        coverage=(CoverageSource("telegram:archive", "checked"),),
        evidence=(_evidence("one", "https://t.me/example/one", title="One", summary="Visible-only source."),),
    )
    invalid_tuples = (
        {"chat_id": "-100123", "actor_id": "42", "owner_chat_id": "42"},
        {"chat_id": "42", "actor_id": None, "owner_chat_id": "42"},
        {"chat_id": "42", "actor_id": "43", "owner_chat_id": "42"},
        {"chat_id": "local-cli", "actor_id": None, "owner_chat_id": None},
    )
    for identity in invalid_tuples:
        assistant = PersonalResearchAssistant(
            settings=SimpleNamespace(db_path=str(db_path)),
            conversations=ConversationStore(),
        )
        result = assistant.answer(OperatorRequest(query="AI", mode="brief", brief_request=request, **identity))
        assert result.payload["brief_document_created"] is True
        assert result.payload["brief_document"]["owner_ref"] == "owner_caller_scope"
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM assistant_brief_documents").fetchone() == (0,)


def test_durable_brief_history_has_an_owner_wide_cap(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "bounded-briefs.db"
    monkeypatch.setenv("AGENT_DB_PATH", str(db_path))
    run_migrations()
    owner_tuple = _owner_tuple("42")
    owner_ref = _owner_ref("42")
    store = BriefDocumentStore(db_path=str(db_path))
    documents = []
    for index in range(65):
        document = build_brief_document(
            BriefBuildRequest(
                topic=f"AI cap {index}", window=_window(), owner_ref=owner_ref,
                coverage=(CoverageSource("telegram:archive", "checked"),),
                evidence=(_evidence(
                    f"cap-{index}", f"https://t.me/example/cap-{index}", title=f"Cap {index}",
                    summary=f"Bounded retained source {index}.",
                ),),
            )
        )
        documents.append(document)
        store.bind_visible(
            conversation_id=f"conversation_cap_{index}",
            response_ref=f"response_{index + 1:024x}",
            document=document,
            authenticated_chat_id=owner_tuple[0], authenticated_actor_id=owner_tuple[1], authenticated_owner_chat_id=owner_tuple[2],
        )
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM assistant_brief_documents WHERE owner_ref = ?", (owner_ref,),
        ).fetchone() == (64,)
    assert store.get_persisted_document(
        authenticated_chat_id=owner_tuple[0], authenticated_actor_id=owner_tuple[1], authenticated_owner_chat_id=owner_tuple[2], brief_id=documents[0].brief_id, version=1,
    ) is None
    assert store.get_persisted_document(
        authenticated_chat_id=owner_tuple[0], authenticated_actor_id=owner_tuple[1], authenticated_owner_chat_id=owner_tuple[2], brief_id=documents[-1].brief_id, version=1,
    ) == documents[-1]


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


def test_active_brief_binds_requested_window_before_archive_candidate_selection(monkeypatch) -> None:
    observed: dict[str, object] = {}
    archive_item = {
        "archive_document_id": "tg:in-window", "source_url": "https://t.me/example/in-window",
        "snippet": "A source selected inside the requested local period.",
        "posted_at": "2026-10-25T10:00:00+02:00", "title": "In-window source", "topics": ["AI"],
    }

    class ProbeFacade:
        def search_telegram_archive(self, query, *, filters, limit):
            observed["query"] = query
            observed["filters"] = dict(filters)
            observed["limit"] = limit
            return {"status": "ok", "items": [
                {**archive_item, "archive_document_id": "tg:outside", "source_url": "https://t.me/example/outside", "posted_at": "2000-01-01T00:00:00Z"},
                archive_item,
            ]}

    def selected_local_payload(_question, *, facade, **_kwargs):
        archive_result = facade.search_telegram_archive(
            "AI", filters={"date_from": "wrong", "date_to": "wrong"}, limit=5,
        )
        return {
            "status": "ok", "direct_answer": "", "answer_gate": {"allow_answer": True},
            "archive_evidence": {"items": archive_result["items"]},
            "evidence_quality": {"items": [{
                "evidence_id": "tg:in-window", "source_url": "https://t.me/example/in-window",
                "support_span": "A source selected inside the requested local period.",
            }]},
            "professional_answer": {}, "project_fit": {}, "project_decision": {}, "claim_ledger": {},
            "unknowns": [], "next_steps": {}, "receipt": {}, "privacy": {},
        }

    monkeypatch.setattr("prm.application.answer_memory_research", selected_local_payload)
    monkeypatch.setattr("prm.application.build_research_facade", lambda **kwargs: ProbeFacade())
    assistant = PersonalResearchAssistant(
        settings=SimpleNamespace(db_path=":memory:"), conversations=ConversationStore(), briefs=BriefDocumentStore(),
    )

    result = assistant.answer(OperatorRequest(
        query="бриф AI с 2026-10-25 по 2026-10-26 timezone Europe/Berlin", mode="brief", chat_id="42",
    ))

    assert observed["filters"] == {
        "date_from": "2026-10-24T22:00:00Z",
        "date_to": "2026-10-25T23:00:00Z",
    }
    assert result.payload["brief_retrieval_window"] == {
        "timezone": "Europe/Berlin",
        "start_at": "2026-10-24T22:00:00Z",
        "end_at": "2026-10-25T23:00:00Z",
        "generated_at": result.payload["brief_retrieval_window"]["generated_at"],
        "interval": "[start_at,end_at)",
        "bound_before_candidate_selection": True,
    }
    assert result.payload["brief_document"]["evidence_refs"] == ["evidence_tg_in-window"]


def test_brief_window_research_facade_never_accepts_a_caller_time_filter() -> None:
    calls: list[dict[str, object]] = []

    class ProbeFacade:
        def search_telegram_archive(self, query, *, filters, limit):
            calls.append(dict(filters))
            return {"status": "ok", "items": [
                {"source_url": "https://t.me/example/outside", "posted_at": "2000-01-01T00:00:00Z"},
                {"source_url": "https://t.me/example/inside", "posted_at": "2026-10-25T10:00:00+02:00"},
            ]}

    bound = BriefWindowResearchFacade(ProbeFacade(), window=_window())
    result = bound.search_telegram_archive(
        "AI", filters={"date_from": "2000-01-01T00:00:00Z", "date_to": "2000-01-02T00:00:00Z"}, limit=3,
    )

    assert calls == [{"date_from": "2026-10-24T22:00:00Z", "date_to": "2026-10-25T23:00:00Z"}]
    assert result["filters"]["brief_window_bound"] is True
    assert result["filters"]["post_selection_rejected_count"] == 1
    assert result["items"] == [{"source_url": "https://t.me/example/inside", "posted_at": "2026-10-25T10:00:00+02:00"}]


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
    assert "Показать полный бриф" in card
    assert "Item 5" not in card
    assert "Item 5" in full
    assert "…" not in full


def test_new_period_or_topic_is_comparison_not_a_version_increment() -> None:
    first = build_brief_document(
        BriefBuildRequest(
            topic="AI", window=_window(), owner_ref="owner_primary", coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_evidence("first", "https://t.me/example/first", title="AI", summary="First week."),),
        )
    )
    next_window = BriefWindow.from_iso(
        timezone_name="Europe/Berlin",
        start_at="2026-10-26T00:00:00+01:00",
        end_at="2026-10-27T00:00:00+01:00",
        generated_at="2026-10-27T01:00:00+01:00",
    )
    next_report = build_brief_document(
        BriefBuildRequest(
            topic="Career", window=next_window, owner_ref="owner_primary",
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_evidence(
                "next", "https://t.me/example/next", title="Career", summary="Next week.",
                posted_at="2026-10-26T10:00:00+01:00", topics=("career",),
            ),),
            previous_document=first,
            comparison_document=first,
        )
    )

    assert next_report.version == 1
    assert next_report.brief_id != first.brief_id
    assert next_report.previous_version is None
    assert next_report.comparison_ref == first.version_ref


def test_brief_preserves_local_archive_temporal_provenance_and_source_state() -> None:
    document = build_brief_document(
        BriefBuildRequest(
            topic="AI",
            window=_window(),
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(
                _evidence(
                    "delayed", "https://t.me/example/delayed", title="Delayed discovery", summary="An older post entered the archive now.",
                    posted_at="2026-10-20T10:00:00+02:00", first_discovered_at="2026-10-25T02:30:00+02:00",
                    source_version="archive-v2",
                ),
                _evidence(
                    "stale", "https://t.me/example/stale", title="Stale source", summary="The retained archive material is stale.",
                    freshness_status="stale",
                ),
                _evidence(
                    "deleted", "https://t.me/example/deleted", title="Deleted source", summary="An older material was removed.",
                    posted_at="2026-10-20T10:00:00+02:00", deleted_at="2026-10-25T11:00:00+02:00",
                ),
                _evidence(
                    "reissued", "https://t.me/example/reissued", title="Reissued source", summary="An older material was reissued.",
                    posted_at="2026-10-20T10:00:00+02:00", reissued_at="2026-10-25T12:00:00+02:00",
                ),
            ),
        )
    )

    evidence = {item["evidence_ref"]: item for item in document.inspect()["evidence"]}
    assert evidence["evidence_delayed"]["time_kind"] == "discovered"
    assert evidence["evidence_delayed"]["period_relation"] == "first_discovered_in_window"
    assert evidence["evidence_delayed"]["published_at"] == "2026-10-20T08:00:00Z"
    assert evidence["evidence_delayed"]["first_discovered_at"] == "2026-10-25T00:30:00Z"
    assert evidence["evidence_delayed"]["source_state"] == "active"
    assert evidence["evidence_delayed"]["source_version"] == "archive-v2"
    assert evidence["evidence_stale"]["source_state"] == "stale"
    assert evidence["evidence_deleted"]["period_relation"] == "deleted_in_window"
    assert evidence["evidence_deleted"]["deleted_at"] == "2026-10-25T09:00:00Z"
    assert evidence["evidence_reissued"]["period_relation"] == "reissued_in_window"
    assert evidence["evidence_reissued"]["reissued_at"] == "2026-10-25T10:00:00Z"
    rendered = render_brief_document(document, view="full")
    assert "впервые обнаружен в периоде" in rendered
    assert "источник помечен как устаревший" in rendered
    assert "источник удалён" in rendered
    assert "источник переиздан" in rendered

    rebuilt = build_brief_document(rebuild_brief_request(document))
    rebuilt_evidence = {item.evidence_ref: item for item in rebuilt.evidence}
    assert rebuilt_evidence["evidence_deleted"].deleted_at == document.evidence_by_ref()["evidence_deleted"].deleted_at
    assert rebuilt_evidence["evidence_reissued"].reissued_at == document.evidence_by_ref()["evidence_reissued"].reissued_at


def test_week_comparison_uses_factual_snapshot_not_only_summary_text() -> None:
    prior_window = BriefWindow.from_iso(
        timezone_name="Europe/Berlin",
        start_at="2026-10-24T00:00:00+02:00",
        end_at="2026-10-25T00:00:00+02:00",
        generated_at="2026-10-25T01:00:00+02:00",
    )
    prior = build_brief_document(
        BriefBuildRequest(
            topic="AI", window=prior_window, owner_ref="owner_primary",
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_evidence(
                "deadline", "https://t.me/example/deadline", title="Deadline", summary="The schedule is retained.",
                posted_at="2026-10-24T10:00:00+02:00", conflict_group="deadline", conflict_value="Monday",
            ),),
        )
    )
    current = build_brief_document(
        BriefBuildRequest(
            topic="AI", window=_window(), owner_ref="owner_primary",
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_evidence(
                "deadline", "https://t.me/example/deadline", title="Deadline", summary="The schedule is retained.",
                conflict_group="deadline", conflict_value="Tuesday", source_version="archive-v2",
            ),),
            comparison_document=prior,
        )
    )

    comparison = render_brief_document(current, view="comparison", comparison_document=prior)
    assert "Изменилось\n- Deadline: https://t.me/example/deadline" in comparison
    assert "Нет зафиксированных изменений по общим источникам." not in comparison
