from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import replace

from db.migrate import run_migrations
from prm.briefs import (
    BriefBuildRequest,
    BriefDocumentStore,
    BriefWindow,
    CoverageSource,
    brief_owner_ref_from_authenticated_private_tuple,
    build_brief_document,
)
from prm.report_exports import PrivateBriefReportReader, REPORT_ACCESS_TTL


def _window() -> BriefWindow:
    return BriefWindow.from_iso(
        timezone_name="Europe/Berlin",
        start_at="2026-10-19T00:00:00+02:00",
        end_at="2026-10-26T00:00:00+01:00",
        generated_at="2026-10-26T01:15:00+01:00",
    )


def _owner_tuple(identifier: str) -> tuple[str, str, str]:
    return identifier, identifier, identifier


def _document(owner_ref: str):
    return build_brief_document(
        BriefBuildRequest(
            topic="Private report",
            owner_ref=owner_ref,
            window=_window(),
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=({
                "local_archive_provenance": True,
                "evidence_id": "private-source",
                "source_url": "https://example.test/private-source",
                "title": "Private source",
                "support_span": "This bounded source remains in the immutable report.",
                "posted_at": "2026-10-21T10:00:00+02:00",
                "topics": ("AI",),
                "importance": "high",
                "urgent": False,
            },),
        )
    )


def _persisted_reader(tmp_path, monkeypatch):
    db_path = tmp_path / "brief-report-access.db"
    monkeypatch.setenv("AGENT_DB_PATH", str(db_path))
    assert run_migrations() == db_path
    owner = _owner_tuple("42")
    owner_ref = brief_owner_ref_from_authenticated_private_tuple(*owner)
    assert owner_ref is not None
    document = _document(owner_ref)
    store = BriefDocumentStore(db_path=str(db_path))
    store.bind_visible(
        conversation_id="conversation_" + "a" * 24,
        response_ref="response_" + "b" * 24,
        document=document,
        authenticated_chat_id=owner[0],
        authenticated_actor_id=owner[1],
        authenticated_owner_chat_id=owner[2],
    )
    return store, document, owner


def test_private_reader_requires_exact_owner_version_digest_and_unexpired_access(tmp_path, monkeypatch) -> None:
    store, document, owner = _persisted_reader(tmp_path, monkeypatch)
    reader = PrivateBriefReportReader(store)
    now = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
    access = reader.open(
        authenticated_chat_id=owner[0], authenticated_actor_id=owner[1], authenticated_owner_chat_id=owner[2],
        brief_id=document.brief_id, version=document.version, now=now,
    )

    assert access is not None
    artifact = reader.render(
        access,
        authenticated_chat_id=owner[0], authenticated_actor_id=owner[1], authenticated_owner_chat_id=owner[2],
        format="markdown", now=now + timedelta(seconds=1),
    )
    assert artifact is not None
    assert artifact.identity.content_digest == document.content_digest

    foreign = _owner_tuple("43")
    assert reader.render(
        access,
        authenticated_chat_id=foreign[0], authenticated_actor_id=foreign[1], authenticated_owner_chat_id=foreign[2],
        format="html", now=now + timedelta(seconds=1),
    ) is None
    assert reader.render(
        replace(access, version=access.version + 1),
        authenticated_chat_id=owner[0], authenticated_actor_id=owner[1], authenticated_owner_chat_id=owner[2],
        format="html", now=now + timedelta(seconds=1),
    ) is None
    assert reader.render(
        access,
        authenticated_chat_id=owner[0], authenticated_actor_id=owner[1], authenticated_owner_chat_id=owner[2],
        format="html", now=now + REPORT_ACCESS_TTL,
    ) is None
    assert reader.open(
        authenticated_chat_id="42", authenticated_actor_id="43", authenticated_owner_chat_id="42",
        brief_id=document.brief_id, version=document.version, now=now,
    ) is None
    assert PrivateBriefReportReader(store).render(
        access,
        authenticated_chat_id=owner[0], authenticated_actor_id=owner[1], authenticated_owner_chat_id=owner[2],
        format="html", now=now + timedelta(seconds=1),
    ) is None


def test_share_preview_has_the_exact_private_artifact_and_never_delivers(tmp_path, monkeypatch) -> None:
    store, document, owner = _persisted_reader(tmp_path, monkeypatch)
    reader = PrivateBriefReportReader(store)
    now = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
    access = reader.open(
        authenticated_chat_id=owner[0], authenticated_actor_id=owner[1], authenticated_owner_chat_id=owner[2],
        brief_id=document.brief_id, version=document.version, now=now,
    )
    assert access is not None

    preview = reader.preview_share(
        access,
        authenticated_chat_id=owner[0], authenticated_actor_id=owner[1], authenticated_owner_chat_id=owner[2],
        recipient_label="Owner's private review inbox", format="html", now=now + timedelta(seconds=1),
    )

    assert preview is not None
    assert preview.recipient_label == "Owner's private review inbox"
    assert preview.delivery_state == "preview_only_no_delivery"
    assert preview.artifact.identity.brief_id == document.brief_id
    assert preview.artifact.identity.version == document.version
    assert preview.artifact.identity.content_digest == document.content_digest
    assert not hasattr(preview, "send")
    assert reader.preview_share(
        access,
        authenticated_chat_id=owner[0], authenticated_actor_id=owner[1], authenticated_owner_chat_id=owner[2],
        recipient_label="   ", format="html", now=now + timedelta(seconds=1),
    ) is None
