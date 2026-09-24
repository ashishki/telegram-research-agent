from datetime import datetime, timedelta, timezone

import pytest

from prm.capabilities import (
    AuthorizationRequest,
    CapabilityDenied,
    CapabilityGrant,
    CapabilityRegistry,
    ProviderPolicy,
    transport_purpose,
)
from prm.memory_library import (
    MEMORY_CAPABILITY,
    MemoryItem,
    MemoryLibraryStore,
    require_memory_access,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
OWNER = "owner_memory_primary"
CONNECTION = "connection_memory_primary"
RESOURCE = "resource_memory_primary"


def _item(ref="memory_note_1", **changes):
    values = {
        "item_ref": ref,
        "owner_ref": OWNER,
        "kind": "note",
        "title": "Idea about evals",
        "content_ref": "content_note_1",
        "source_ref": "source_note_1",
        "state": "active",
        "engagement": "indexed",
        "version": 1,
        "content_digest": "a" * 64,
        "saved_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return MemoryItem(**values)  # type: ignore[arg-type]


def _store(tmp_path):
    return MemoryLibraryStore(tmp_path / "memory.db")


def _registry():
    grant = CapabilityGrant(
        grant_id="grant_memory_primary",
        owner_ref=OWNER,
        connection_ref=CONNECTION,
        capability=MEMORY_CAPABILITY,
        resource_refs=(RESOURCE,),
        operations=("read", "write", "delete"),
        data_classes=("private_connector_metadata",),
        purpose="memory.manage",
        provider_policy=ProviderPolicy(("provider_local",), maximum_request_count=8),
        issued_at=NOW.replace(microsecond=0),
        expires_at=NOW + timedelta(minutes=10),
        revision=1,
    )
    return CapabilityRegistry((grant,))


def _decision(operation):
    return _registry().authorize_and_reserve(
        AuthorizationRequest(
            owner_ref=OWNER,
            connection_ref=CONNECTION,
            capability=MEMORY_CAPABILITY,
            resource_ref=RESOURCE,
            operation=operation,
            data_class="private_connector_metadata",
            provider_ref="provider_local",
            purpose="memory.manage",
            operation_ref=f"operation_memory_{operation}",
        ),
        now=NOW,
    )


def test_engagement_states_are_not_conflated(tmp_path):
    store = _store(tmp_path)
    store.save_item(_item())
    assert store.get_item(OWNER, "memory_note_1").engagement == "indexed"
    store.set_engagement(OWNER, "memory_note_1", "read", now=NOW)
    read = store.get_item(OWNER, "memory_note_1")
    assert read.engagement == "read"
    store.set_engagement(OWNER, "memory_note_1", "applied", now=NOW)
    assert store.get_item(OWNER, "memory_note_1").engagement == "applied"
    # An "opened" item is not "read" and not "applied".
    store.set_engagement(OWNER, "memory_note_1", "opened", now=NOW)
    assert store.get_item(OWNER, "memory_note_1").engagement == "opened"


def test_revision_preserves_history(tmp_path):
    store = _store(tmp_path)
    store.save_item(_item())
    revised = store.revise_item(OWNER, "memory_note_1", title="Idea about evals v2", content_ref="content_note_2", now=NOW)
    assert revised.version == 2
    history = store.item_history(OWNER, "memory_note_1")
    assert [item.version for item in history] == [1, 2]
    assert history[0].title == "Idea about evals"


def test_forget_marks_item_and_returns_explicit_propagation_plan(tmp_path):
    store = _store(tmp_path)
    store.save_item(_item())
    store.save_item(_item(ref="memory_note_2", content_ref="content_note_2"))
    plan = store.forget_item(OWNER, "memory_note_1", now=NOW)
    assert plan.item_ref == "memory_note_1"
    assert {target for target, _ in plan.targets} == {"index", "cache", "jobs"}
    assert store.get_item(OWNER, "memory_note_1").state == "forgotten"
    # Unrelated items are untouched.
    assert store.get_item(OWNER, "memory_note_2").state == "active"
    assert [item.item_ref for item in store.list_items(OWNER)] == ["memory_note_2"]


def test_feedback_preference_needs_confirmation_and_is_reversible(tmp_path):
    store = _store(tmp_path)
    proposal = store.propose_preference(
        OWNER, kind="interest", value="agent evals", source="feedback",
        evidence_refs=("evidence_1",), now=NOW,
    )
    with pytest.raises(ValueError):
        store.confirm_preference(proposal, owner_ref="someone_else", now=NOW)
    pref = store.confirm_preference(proposal, owner_ref=OWNER, now=NOW)
    assert pref.revision == 1 and pref.active
    assert [p.value for p in store.active_preferences(OWNER)] == ["agent evals"]
    # Re-applying the same proposal is refused (one-use).
    with pytest.raises(ValueError):
        store.confirm_preference(proposal, owner_ref=OWNER, now=NOW)
    deactivated = store.deactivate_preference(OWNER, pref.preference_ref, now=NOW)
    assert deactivated.active is False
    assert store.active_preferences(OWNER) == ()
    assert len(store.history_preferences(OWNER)) == 2  # both revisions retained


def test_export_exposes_lifecycle_source_and_time(tmp_path):
    store = _store(tmp_path)
    store.save_item(_item())
    exported = store.export_items(OWNER)
    assert exported[0]["engagement"] == "indexed"
    assert exported[0]["source_ref"] == "source_note_1"
    assert exported[0]["saved_at"]


def test_memory_access_fails_closed_without_reservation():
    with pytest.raises(CapabilityDenied):
        require_memory_access(
            None, owner_ref=OWNER, connection_ref=CONNECTION, resource_ref=RESOURCE, operation="write"
        )
    require_memory_access(
        _decision("write"), owner_ref=OWNER, connection_ref=CONNECTION, resource_ref=RESOURCE, operation="write"
    )
    assert (
        transport_purpose(provider_ref="provider_local", capability=MEMORY_CAPABILITY, operation="delete")
        == "memory.manage"
    )
