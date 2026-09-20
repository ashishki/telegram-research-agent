"""PA-09 local subscription-policy holdouts; no account, service or timer."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from prm.capabilities import AuthorizationRequest, CapabilityGrant, CapabilityRegistry, ProviderPolicy
from prm.watch_jobs import WatchCollectionAccess, WatchJobStore, WatchNotification, WatchSubscription, watch_owner_ref_from_authenticated_private_tuple


NOW = datetime.now(timezone.utc).replace(microsecond=0)
OWNER_TUPLE = ("42", "42", "42")
OWNER_REF = watch_owner_ref_from_authenticated_private_tuple(*OWNER_TUPLE)
assert OWNER_REF is not None


def _subscription(**changes: object) -> WatchSubscription:
    values: dict[str, object] = {
        "subscription_id": "watch_synthetic_001",
        "owner_ref": OWNER_REF,
        "consent_revision": 1,
        "source_refs": ("source_synthetic_calendar",),
        "destination_ref": "destination_private_telegram",
        "trigger": "meaningful_change",
        "timezone_name": "America/New_York",
        "expires_at": NOW + timedelta(days=30),
        "daily_cap": 2,
        "quiet_start": "22:00",
        "quiet_end": "08:00",
    }
    values.update(changes)
    return WatchSubscription(**values)  # type: ignore[arg-type]


def _notification(**changes: object) -> WatchNotification:
    values: dict[str, object] = {
        "subscription_id": "watch_synthetic_001",
        "owner_ref": OWNER_REF,
        "subject_ref": "subject_deadline_001",
        "change_version": "version_001",
        "delivery_stage": "change",
        "title": "Registration deadline changed",
        "change_summary": "The confirmed deadline moved from Monday to Wednesday.",
        "relevance_reason": "It applies to the selected programme deadline.",
        "source_ref": "source_synthetic_calendar",
        "due_at": NOW,
    }
    values.update(changes)
    return WatchNotification(**values)  # type: ignore[arg-type]


def _collection_access(registry: CapabilityRegistry):
    decision = registry.authorize_and_reserve(
        AuthorizationRequest(
            owner_ref=OWNER_REF, connection_ref=None, capability="assistant.watch_collection",
            resource_ref="source_synthetic_calendar", operation="read", data_class="private_connector_metadata",
            provider_ref="provider_watch_source", purpose="watch.collection",
        ), now=NOW,
    )
    return WatchCollectionAccess(decision, OWNER_REF, "source_synthetic_calendar")


def _read_grant(*, revoked: bool = False) -> CapabilityGrant:
    return CapabilityGrant(
        grant_id="grant_watch_read_001", owner_ref=OWNER_REF, connection_ref=None,
        capability="assistant.watch_collection", resource_refs=("source_synthetic_calendar",), operations=("read",),
        data_classes=("private_connector_metadata",), purpose="watch.collection",
        provider_policy=ProviderPolicy(("provider_watch_source",), maximum_request_count=2),
        issued_at=NOW - timedelta(hours=1), expires_at=NOW + timedelta(hours=1), revision=1,
        revoked_at=NOW - timedelta(seconds=1) if revoked else None,
    )


def _register(store: WatchJobStore, subscription: WatchSubscription) -> WatchSubscription:
    registered = store.register_subscription(
        subscription,
        authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1],
        authenticated_owner_chat_id=OWNER_TUPLE[2],
    )
    assert registered is not None
    return registered


def test_collection_rechecks_active_subscription_and_current_read_grant(tmp_path) -> None:
    store = WatchJobStore(tmp_path / "watch-jobs.db")
    subscription = _register(store, _subscription())
    assert store.collection_allowed(subscription.subscription_id, _collection_access(CapabilityRegistry((_read_grant(),))), now=NOW)

    revoked_registry = CapabilityRegistry((_read_grant(),))
    access = _collection_access(revoked_registry)
    revoked_registry.revoke_grant("grant_watch_read_001", revoked_at=NOW)
    assert not store.collection_allowed(subscription.subscription_id, access, now=NOW)

    paused = replace(subscription, consent_revision=2, lifecycle="paused")
    assert store.revise_subscription(paused, expected_revision=1, authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1], authenticated_owner_chat_id=OWNER_TUPLE[2], now=NOW)
    assert not store.collection_allowed(paused.subscription_id, _collection_access(CapabilityRegistry((_read_grant(),))), now=NOW)


def test_queue_requires_source_scope_material_change_and_exact_revision(tmp_path) -> None:
    store = WatchJobStore(tmp_path / "watch-jobs.db")
    _register(store, _subscription())
    notification = _notification()
    first = store.queue_notification(notification, expected_subscription_revision=1, now=NOW)
    assert first.status == "queued" and first.job is not None
    assert store.queue_notification(notification, expected_subscription_revision=1, now=NOW).status == "duplicate"
    assert store.queue_notification(notification, expected_subscription_revision=2, now=NOW).reason == "subscription_revision_mismatch"
    assert store.queue_notification(replace(notification, source_ref="source_unconfirmed"), expected_subscription_revision=1, now=NOW).reason == "source_not_confirmed"

    try:
        _notification(change_summary="")
    except ValueError as exc:
        assert "change_summary" in str(exc)
    else:
        raise AssertionError("a timestamp-only update must not become an alert")

    try:
        _notification(delivery_stage="change:noise")
    except ValueError as exc:
        assert "delivery_stage" in str(exc)
    else:
        raise AssertionError("a caller must not manufacture extra change stages")


def test_quiet_hours_and_dst_schedule_do_not_turn_an_ordinary_digest_into_a_flood(tmp_path) -> None:
    store = WatchJobStore(tmp_path / "watch-jobs.db")
    spring_queue_time = datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc)
    digest = _subscription(
        trigger="digest", delivery_time="02:30", quiet_start=None, quiet_end=None,
        frequency="daily", expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )
    _register(store, digest)
    notification = _notification(delivery_stage="digest:2026-03-08", change_version="version_digest_001", due_at=spring_queue_time)
    queued = store.queue_notification(notification, expected_subscription_revision=1, now=spring_queue_time)
    assert queued.job is not None
    # 02:30 does not exist in New York on this spring-forward day. The first
    # bounded post-gap worker can claim it; a receipt then prevents a repeat.
    spring_forward = datetime(2026, 3, 8, 7, 5, tzinfo=timezone.utc)
    claimed = store.claim_due_jobs(now=spring_forward)
    assert len(claimed) == 1
    assert store.claim_due_jobs(now=spring_forward + timedelta(minutes=30)) == ()

    quiet_store = WatchJobStore(tmp_path / "quiet.db")
    _register(quiet_store, _subscription())
    quiet = quiet_store.queue_notification(_notification(), expected_subscription_revision=1, now=NOW)
    assert quiet.job is not None
    assert quiet_store.claim_due_jobs(now=datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)) == ()  # 01:30 local
