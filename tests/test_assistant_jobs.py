"""PA-09 durable-job/reconciliation holdouts; all state is temporary SQLite."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Barrier, Thread

from prm.capabilities import AuthorizationRequest, CapabilityGrant, CapabilityRegistry, ProviderPolicy
from prm.watch_jobs import WatchDeliveryAccess, WatchJobStore, WatchNotification, WatchSubscription


NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _subscription(**changes: object) -> WatchSubscription:
    values: dict[str, object] = {
        "subscription_id": "watch_synthetic_101", "owner_ref": "owner_synthetic_primary", "consent_revision": 1,
        "source_refs": ("source_synthetic_calendar",), "destination_ref": "destination_private_telegram",
        "trigger": "meaningful_change", "timezone_name": "Europe/Berlin", "expires_at": NOW + timedelta(days=30),
        "daily_cap": 2,
    }
    values.update(changes)
    return WatchSubscription(**values)  # type: ignore[arg-type]


def _notification(**changes: object) -> WatchNotification:
    values: dict[str, object] = {
        "subscription_id": "watch_synthetic_101", "owner_ref": "owner_synthetic_primary", "subject_ref": "subject_due_101",
        "change_version": "version_101", "delivery_stage": "change", "title": "Deadline changed",
        "change_summary": "The source moved the deadline to Tuesday.",
        "relevance_reason": "This is a selected personal deadline.", "source_ref": "source_synthetic_calendar", "due_at": NOW,
    }
    values.update(changes)
    return WatchNotification(**values)  # type: ignore[arg-type]


def _delivery_registry() -> CapabilityRegistry:
    grant = CapabilityGrant(
        grant_id="grant_watch_delivery_101", owner_ref="owner_synthetic_primary", connection_ref=None,
        capability="assistant.watch_delivery", resource_refs=("destination_private_telegram",), operations=("deliver",),
        data_classes=("model_generated",), purpose="watch.delivery",
        provider_policy=ProviderPolicy(("provider_telegram",), maximum_request_count=4),
        issued_at=NOW - timedelta(hours=1), expires_at=NOW + timedelta(hours=1), revision=1,
    )
    return CapabilityRegistry((grant,))


def _delivery_access(registry: CapabilityRegistry, *, operation_ref: str | None = None) -> WatchDeliveryAccess:
    decision = registry.authorize_and_reserve(
        AuthorizationRequest(
            owner_ref="owner_synthetic_primary", connection_ref=None, capability="assistant.watch_delivery",
            resource_ref="destination_private_telegram", operation="deliver", data_class="model_generated",
            provider_ref="provider_telegram", purpose="watch.delivery", operation_ref=operation_ref,
        ), now=NOW,
    )
    return WatchDeliveryAccess(decision, "owner_synthetic_primary", "destination_private_telegram", "model_generated")


def _queued(store: WatchJobStore, notification: WatchNotification | None = None):
    store.register_subscription(_subscription())
    result = store.queue_notification(notification or _notification(), expected_subscription_revision=1, now=NOW)
    assert result.job is not None
    return result.job


def test_changed_version_and_completed_subject_cancel_waiting_or_leased_jobs(tmp_path) -> None:
    store = WatchJobStore(tmp_path / "jobs.db")
    old = _queued(store)
    replacement = _notification(change_version="version_102", change_summary="The source moved the deadline to Wednesday.")
    newer = store.queue_notification(replacement, expected_subscription_revision=1, now=NOW)
    assert newer.status == "queued" and store.job_state(old.job_key) == "cancelled"
    claimed = store.claim_due_jobs(now=NOW)
    assert len(claimed) == 1
    assert store.complete_subject("watch_synthetic_101", "subject_due_101", expected_subscription_revision=1, now=NOW)
    assert store.prepare_delivery(claimed[0], _delivery_access(_delivery_registry()), now=NOW) is None
    assert store.job_state(claimed[0].job_key) == "cancelled"


def test_one_lease_wins_and_expired_lease_becomes_unknown_until_reconciliation(tmp_path) -> None:
    store = WatchJobStore(tmp_path / "jobs.db")
    queued = _queued(store)
    barrier = Barrier(2)
    claims: list[tuple] = []

    def claim() -> None:
        barrier.wait()
        claims.append(store.claim_due_jobs(now=NOW))

    first, second = Thread(target=claim), Thread(target=claim)
    first.start(); second.start(); first.join(); second.join()
    assert sorted(len(value) for value in claims) == [0, 1]
    assert store.job_state(queued.job_key) == "leased"
    assert store.claim_due_jobs(now=NOW + timedelta(minutes=2)) == ()
    assert store.job_state(queued.job_key) == "unknown"
    assert store.reconcile_unknown(queued.job_key, outcome="not_delivered", now=NOW + timedelta(minutes=2))
    assert len(store.claim_due_jobs(now=NOW + timedelta(minutes=2))) == 1


def test_revoked_delivery_grant_blocks_final_send_and_unknown_is_never_blindly_retried(tmp_path) -> None:
    store = WatchJobStore(tmp_path / "jobs.db")
    queued = _queued(store)
    leased = store.claim_due_jobs(now=NOW)[0]
    registry = _delivery_registry()
    access = _delivery_access(registry, operation_ref="operation_watch_101")
    registry.revoke_grant("grant_watch_delivery_101", revoked_at=NOW)
    assert store.prepare_delivery(leased, access, now=NOW) is None
    assert store.job_state(queued.job_key) == "cancelled" and store.receipt(queued.job_key) is None

    unknown_store = WatchJobStore(tmp_path / "unknown.db")
    _queued(unknown_store)
    leased = unknown_store.claim_due_jobs(now=NOW)[0]
    attempt = unknown_store.prepare_delivery(leased, _delivery_access(_delivery_registry()), now=NOW)
    assert attempt is not None
    assert unknown_store.finish_delivery(attempt, outcome="unknown", detail="fixture timeout", now=NOW)
    assert unknown_store.job_state(leased.job_key) == "unknown"
    assert unknown_store.claim_due_jobs(now=NOW + timedelta(days=1)) == ()
    assert unknown_store.reconcile_unknown(leased.job_key, outcome="delivered", transport_receipt_ref="receipt_fixture_101", now=NOW)
    assert unknown_store.receipt(leased.job_key) is not None


def test_receipt_is_separate_from_job_state_and_daily_cap_is_conservative(tmp_path) -> None:
    store = WatchJobStore(tmp_path / "jobs.db")
    first = _queued(store)
    second_notification = _notification(subject_ref="subject_due_102", change_version="version_102")
    second = store.queue_notification(second_notification, expected_subscription_revision=1, now=NOW)
    assert second.job is not None
    registry = _delivery_registry()
    lease = {job.job_key: job for job in store.claim_due_jobs(now=NOW)}
    attempt = store.prepare_delivery(lease[first.job_key], _delivery_access(registry), now=NOW)
    assert attempt is not None and "Что изменилось" in attempt.text and "Почему это важно" in attempt.text
    assert store.receipt(first.job_key) is None
    assert store.finish_delivery(attempt, outcome="sent", transport_receipt_ref="receipt_fixture_102", now=NOW)
    assert store.job_state(first.job_key) == "sent" and store.receipt(first.job_key)["outcome"] == "sent"  # type: ignore[index]

    # A revision with a cap of one refuses the next final preflight rather than
    # sending it and attempting to correct the quota afterward.
    capped = replace(_subscription(), consent_revision=2, daily_cap=1)
    assert store.revise_subscription(capped, expected_revision=1, now=NOW)
    again = store.queue_notification(_notification(subject_ref="subject_due_103", change_version="version_103"), expected_subscription_revision=2, now=NOW)
    assert again.job is not None
    lease = store.claim_due_jobs(now=NOW)
    assert len(lease) == 1
    assert store.prepare_delivery(lease[0], _delivery_access(registry), now=NOW) is None
    assert store.job_state(lease[0].job_key) == "cancelled"


def test_explicit_feedback_pauses_or_unsubscribes_without_claiming_a_hidden_preference(tmp_path) -> None:
    store = WatchJobStore(tmp_path / "feedback.db")
    first = _queued(store)
    leased = store.claim_due_jobs(now=NOW)[0]
    attempt = store.prepare_delivery(leased, _delivery_access(_delivery_registry()), now=NOW)
    assert attempt is not None and store.finish_delivery(attempt, outcome="sent", now=NOW)
    assert store.record_feedback(first.job_key, action="less", now=NOW)
    assert store.subscription("watch_synthetic_101").lifecycle == "active"  # type: ignore[union-attr]
    assert store.record_feedback(first.job_key, action="pause", now=NOW)
    paused = store.subscription("watch_synthetic_101")
    assert paused is not None and paused.lifecycle == "paused" and paused.consent_revision == 2
    assert store.queue_notification(_notification(subject_ref="subject_due_102", change_version="version_102"), expected_subscription_revision=2, now=NOW).reason == "paused"

    unsubscribe = WatchJobStore(tmp_path / "unsubscribe.db")
    job = _queued(unsubscribe)
    leased = unsubscribe.claim_due_jobs(now=NOW)[0]
    attempt = unsubscribe.prepare_delivery(leased, _delivery_access(_delivery_registry()), now=NOW)
    assert attempt is not None and unsubscribe.finish_delivery(attempt, outcome="sent", now=NOW)
    assert unsubscribe.record_feedback(job.job_key, action="unsubscribe", now=NOW)
    stopped = unsubscribe.subscription("watch_synthetic_101")
    assert stopped is not None and stopped.lifecycle == "cancelled" and stopped.consent_revision == 2


def test_one_shot_runner_owns_final_preflight_but_has_no_default_transport(tmp_path) -> None:
    store = WatchJobStore(tmp_path / "runner.db")
    _queued(store)
    registry = _delivery_registry()
    sent: list[str] = []
    result = store.run_once(
        access_for_job=lambda _job: _delivery_access(registry),
        sender=lambda text: sent.append(text) or "receipt_runner_101",
        now=NOW,
    )
    assert result.claimed == result.sent == 1 and result.unknown == result.deferred == result.blocked == 0
    assert len(sent) == 1 and "Почему это важно" in sent[0]

    blocked = WatchJobStore(tmp_path / "runner-blocked.db")
    _queued(blocked)
    no_transport = blocked.run_once(
        access_for_job=lambda _job: None,
        sender=lambda _text: (_ for _ in ()).throw(AssertionError("must not send")),
        now=NOW,
    )
    assert no_transport.claimed == no_transport.blocked == 1 and no_transport.sent == 0
