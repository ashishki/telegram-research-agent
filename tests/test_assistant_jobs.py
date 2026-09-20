"""PA-09 durable-job/reconciliation holdouts; all state is temporary SQLite."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from itertools import count
from threading import Barrier, Event, Thread

import pytest

from prm.capabilities import AuthorizationRequest, CapabilityGrant, CapabilityRegistry, ProviderPolicy
from prm.watch_jobs import WatchDeliveryAccess, WatchJobStore, WatchNotification, WatchReconciliationEvidence, WatchSubscription, watch_owner_ref_from_authenticated_private_tuple


NOW = datetime.now(timezone.utc).replace(microsecond=0)
OWNER_TUPLE = ("42", "42", "42")
OWNER_REF = watch_owner_ref_from_authenticated_private_tuple(*OWNER_TUPLE)
assert OWNER_REF is not None
_OPERATION_SEQUENCE = count(1000)


def _subscription(**changes: object) -> WatchSubscription:
    values: dict[str, object] = {
        "subscription_id": "watch_synthetic_101", "owner_ref": OWNER_REF, "consent_revision": 1,
        "source_refs": ("source_synthetic_calendar",), "destination_ref": "destination_private_telegram",
        "trigger": "meaningful_change", "timezone_name": "Europe/Berlin", "expires_at": NOW + timedelta(days=30),
        "daily_cap": 2,
    }
    values.update(changes)
    return WatchSubscription(**values)  # type: ignore[arg-type]


def _notification(**changes: object) -> WatchNotification:
    values: dict[str, object] = {
        "subscription_id": "watch_synthetic_101", "owner_ref": OWNER_REF, "subject_ref": "subject_due_101",
        "change_version": "version_101", "delivery_stage": "change", "title": "Deadline changed",
        "change_summary": "The source moved the deadline to Tuesday.",
        "relevance_reason": "This is a selected personal deadline.", "source_ref": "source_synthetic_calendar", "due_at": NOW,
    }
    values.update(changes)
    return WatchNotification(**values)  # type: ignore[arg-type]


def _delivery_registry() -> CapabilityRegistry:
    grant = CapabilityGrant(
        grant_id="grant_watch_delivery_101", owner_ref=OWNER_REF, connection_ref=None,
        capability="assistant.watch_delivery", resource_refs=("destination_private_telegram",), operations=("deliver",),
        data_classes=("model_generated",), purpose="watch.delivery",
        provider_policy=ProviderPolicy(("provider_telegram",), maximum_request_count=4),
        issued_at=NOW - timedelta(hours=1), expires_at=NOW + timedelta(hours=1), revision=1,
    )
    return CapabilityRegistry((grant,))


def _delivery_access(registry: CapabilityRegistry, *, operation_ref: str | None = None) -> WatchDeliveryAccess:
    if operation_ref is None:
        operation_ref = f"operation_watch_{next(_OPERATION_SEQUENCE)}"
    decision = registry.authorize_and_reserve(
        AuthorizationRequest(
            owner_ref=OWNER_REF, connection_ref=None, capability="assistant.watch_delivery",
            resource_ref="destination_private_telegram", operation="deliver", data_class="model_generated",
            provider_ref="provider_telegram", purpose="watch.delivery", operation_ref=operation_ref,
        ), now=NOW,
    )
    return WatchDeliveryAccess(decision, OWNER_REF, "destination_private_telegram", "model_generated")


def _queued(store: WatchJobStore, notification: WatchNotification | None = None):
    preview = store.preview_subscription(_subscription(), authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1], authenticated_owner_chat_id=OWNER_TUPLE[2])
    assert preview is not None
    registered = store.confirm_subscription(preview.confirmation_ref, authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1], authenticated_owner_chat_id=OWNER_TUPLE[2])
    assert registered is not None
    result = store.queue_notification(notification or _notification(), expected_subscription_revision=1, now=NOW)
    assert result.job is not None
    return result.job


def _revise(store: WatchJobStore, subscription: WatchSubscription) -> WatchSubscription:
    preview = store.preview_subscription(subscription, authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1], authenticated_owner_chat_id=OWNER_TUPLE[2], now=NOW)
    assert preview is not None
    revised = store.confirm_subscription(preview.confirmation_ref, authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1], authenticated_owner_chat_id=OWNER_TUPLE[2], now=NOW)
    assert revised is not None
    return revised


def test_changed_version_and_completed_subject_cancel_waiting_or_leased_jobs(tmp_path) -> None:
    store = WatchJobStore(tmp_path / "jobs.db")
    old = _queued(store)
    replacement = _notification(change_version="version_102", change_summary="The source moved the deadline to Wednesday.")
    newer = store.queue_notification(replacement, expected_subscription_revision=1, now=NOW)
    assert newer.status == "queued" and store.job_state(old.job_key) == "cancelled"
    claimed = store.claim_due_jobs(now=NOW)
    assert len(claimed) == 1
    assert store.complete_subject("watch_synthetic_101", "subject_due_101", expected_subscription_revision=1, authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1], authenticated_owner_chat_id=OWNER_TUPLE[2], now=NOW)
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
    # A crash/expired lease has no durable PA-02 operation record. It is
    # deliberately unknown and cannot be relabelled as a safe retry.
    assert store.reconciliation_requirement(
        queued.job_key, authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1],
        authenticated_owner_chat_id=OWNER_TUPLE[2],
    ) is None
    assert store.claim_due_jobs(now=NOW + timedelta(days=1)) == ()


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
    unknown_registry = _delivery_registry()
    unknown_access = _delivery_access(unknown_registry)
    assert unknown_store.deliver_claimed_job(
        leased, unknown_access,
        sender=lambda _text: (_ for _ in ()).throw(RuntimeError("fixture timeout")), now=NOW,
    ) == "unknown"
    assert unknown_store.job_state(leased.job_key) == "unknown"
    assert unknown_store.claim_due_jobs(now=NOW + timedelta(days=1)) == ()
    requirement = unknown_store.reconciliation_requirement(
        leased.job_key, authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1],
        authenticated_owner_chat_id=OWNER_TUPLE[2],
    )
    assert requirement is not None
    assert unknown_store.reconciliation_requirement(
        leased.job_key, authenticated_chat_id="43", authenticated_actor_id="43", authenticated_owner_chat_id="43",
    ) is None
    assert not unknown_store.reconcile_unknown(
        WatchReconciliationEvidence(leased.job_key, OWNER_REF, requirement.destination_ref, "operation_wrong_101", requirement.attempt_ref, "delivered", "receipt_fixture_101", NOW),
        authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1], authenticated_owner_chat_id=OWNER_TUPLE[2],
    )
    assert not unknown_store.reconcile_unknown(
        WatchReconciliationEvidence(leased.job_key, OWNER_REF, requirement.destination_ref, requirement.operation_ref, requirement.attempt_ref, "delivered", "receipt_fixture_101", NOW),
        authenticated_chat_id="43", authenticated_actor_id="43", authenticated_owner_chat_id="43",
    )
    assert unknown_store.reconcile_unknown(
        WatchReconciliationEvidence(leased.job_key, OWNER_REF, requirement.destination_ref, requirement.operation_ref, requirement.attempt_ref, "delivered", "receipt_fixture_101", NOW),
        authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1], authenticated_owner_chat_id=OWNER_TUPLE[2],
    )
    assert unknown_store.receipt(leased.job_key) is not None


def test_restart_after_sender_started_preserves_bound_unknown_reconciliation(tmp_path) -> None:
    path = tmp_path / "crash-during-send.db"
    store = WatchJobStore(path)
    queued = _queued(store)
    leased = store.claim_due_jobs(now=NOW)[0]
    registry = _delivery_registry()

    def crash_after_sender_started(_text: str) -> str:
        raise SystemExit("synthetic process loss after sender start")

    with pytest.raises(SystemExit, match="process loss"):
        store.deliver_claimed_job(leased, _delivery_access(registry), sender=crash_after_sender_started, now=NOW)
    restarted = WatchJobStore(path)
    assert restarted.claim_due_jobs(now=NOW + timedelta(minutes=2)) == ()
    assert restarted.job_state(queued.job_key) == "unknown"
    requirement = restarted.reconciliation_requirement(
        queued.job_key, authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1],
        authenticated_owner_chat_id=OWNER_TUPLE[2],
    )
    assert requirement is not None
    assert restarted.reconcile_unknown(
        WatchReconciliationEvidence(
            queued.job_key, OWNER_REF, requirement.destination_ref, requirement.operation_ref,
            requirement.attempt_ref, "not_delivered", "provider_receipt_after_restart_001", NOW + timedelta(minutes=2),
        ),
        authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1], authenticated_owner_chat_id=OWNER_TUPLE[2],
    )
    assert len(restarted.claim_due_jobs(now=NOW + timedelta(minutes=2))) == 1


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
    assert store.deliver_claimed_job(lease[first.job_key], _delivery_access(registry), sender=lambda _text: "receipt_fixture_102", now=NOW) == "sent"
    assert store.job_state(first.job_key) == "sent" and store.receipt(first.job_key)["outcome"] == "sent"  # type: ignore[index]

    # A revision with a cap of one refuses the next final preflight rather than
    # sending it and attempting to correct the quota afterward.
    capped = replace(_subscription(), consent_revision=2, daily_cap=1)
    assert _revise(store, capped) == capped
    again = store.queue_notification(_notification(subject_ref="subject_due_103", change_version="version_103"), expected_subscription_revision=2, now=NOW)
    assert again.job is not None
    lease = store.claim_due_jobs(now=NOW)
    assert len(lease) == 1
    assert store.deliver_claimed_job(lease[0], _delivery_access(registry), sender=lambda _text: (_ for _ in ()).throw(AssertionError("must not send")), now=NOW) == "blocked"
    assert store.job_state(lease[0].job_key) == "cancelled"


def test_explicit_feedback_pauses_or_unsubscribes_without_claiming_a_hidden_preference(tmp_path) -> None:
    store = WatchJobStore(tmp_path / "feedback.db")
    first = _queued(store)
    leased = store.claim_due_jobs(now=NOW)[0]
    attempt = store.prepare_delivery(leased, _delivery_access(_delivery_registry()), now=NOW)
    assert attempt is not None and store.finish_delivery(attempt, outcome="sent", now=NOW)
    assert not store.record_feedback(first.job_key, action="pause", authenticated_chat_id="43", authenticated_actor_id="43", authenticated_owner_chat_id="43", now=NOW)
    assert store.subscription("watch_synthetic_101").lifecycle == "active"  # type: ignore[union-attr]
    assert store.record_feedback(first.job_key, action="less", authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1], authenticated_owner_chat_id=OWNER_TUPLE[2], now=NOW)
    assert store.subscription("watch_synthetic_101").lifecycle == "active"  # type: ignore[union-attr]
    assert store.record_feedback(first.job_key, action="pause", authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1], authenticated_owner_chat_id=OWNER_TUPLE[2], now=NOW)
    paused = store.subscription("watch_synthetic_101")
    assert paused is not None and paused.lifecycle == "paused" and paused.consent_revision == 2
    assert store.queue_notification(_notification(subject_ref="subject_due_102", change_version="version_102"), expected_subscription_revision=2, now=NOW).reason == "paused"

    unsubscribe = WatchJobStore(tmp_path / "unsubscribe.db")
    job = _queued(unsubscribe)
    leased = unsubscribe.claim_due_jobs(now=NOW)[0]
    attempt = unsubscribe.prepare_delivery(leased, _delivery_access(_delivery_registry()), now=NOW)
    assert attempt is not None and unsubscribe.finish_delivery(attempt, outcome="sent", now=NOW)
    assert unsubscribe.record_feedback(job.job_key, action="unsubscribe", authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1], authenticated_owner_chat_id=OWNER_TUPLE[2], now=NOW)
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
    blocked_job = _queued(blocked)
    no_transport = blocked.run_once(
        access_for_job=lambda _job: None,
        sender=lambda _text: (_ for _ in ()).throw(AssertionError("must not send")),
        now=NOW,
    )
    assert no_transport.claimed == no_transport.blocked == 1 and no_transport.sent == 0
    assert blocked.job_state(blocked_job.job_key) == "cancelled"
    job = blocked.claim_due_jobs(now=NOW + timedelta(minutes=2))
    assert job == ()  # known no-send was cancelled, not converted to unknown


def test_delivery_holds_one_terminal_transaction_across_sender_and_prevents_double_send(tmp_path) -> None:
    store = WatchJobStore(tmp_path / "terminal-lease.db")
    queued = _queued(store)
    leased = store.claim_due_jobs(now=NOW)[0]
    registry = _delivery_registry()
    first_access = _delivery_access(registry)
    second_access = _delivery_access(registry)
    entered, release = Event(), Event()
    sender_calls: list[str] = []
    outcomes: list[str] = []

    def sender(_text: str) -> str:
        sender_calls.append("called")
        entered.set()
        assert release.wait(timeout=2)
        return "receipt_terminal_lease_001"

    first = Thread(target=lambda: outcomes.append(store.deliver_claimed_job(leased, first_access, sender=sender, now=NOW)))
    first.start()
    assert entered.wait(timeout=2)
    second = Thread(target=lambda: outcomes.append(store.deliver_claimed_job(
        leased, second_access, sender=lambda _text: (_ for _ in ()).throw(AssertionError("second sender must not run")), now=NOW,
    )))
    second.start()
    assert sender_calls == ["called"]
    release.set()
    first.join(timeout=3); second.join(timeout=3)
    assert not first.is_alive() and not second.is_alive()
    assert sorted(outcomes) == ["blocked", "sent"]
    assert sender_calls == ["called"] and store.job_state(queued.job_key) == "sent"


def test_restart_keeps_subscription_receipt_and_idempotency_state_without_replay(tmp_path) -> None:
    path = tmp_path / "restart-sidecar.db"
    original = WatchJobStore(path)
    queued = _queued(original)
    recovered = WatchJobStore(path)
    claimed = recovered.claim_due_jobs(now=NOW)
    assert len(claimed) == 1 and claimed[0].job_key == queued.job_key
    assert recovered.deliver_claimed_job(
        claimed[0], _delivery_access(_delivery_registry()), sender=lambda _text: "receipt_restart_001", now=NOW,
    ) == "sent"
    restarted = WatchJobStore(path)
    assert restarted.subscription("watch_synthetic_101") is not None
    assert restarted.receipt(queued.job_key) is not None
    assert restarted.claim_due_jobs(now=NOW + timedelta(days=1)) == ()
    assert restarted.queue_notification(_notification(), expected_subscription_revision=1, now=NOW).reason == "same_subject_version_stage"


def test_pause_revision_cannot_commit_between_terminal_policy_and_sender(tmp_path) -> None:
    store = WatchJobStore(tmp_path / "terminal-pause-linearized.db")
    queued = _queued(store)
    leased = store.claim_due_jobs(now=NOW)[0]
    current = store.subscription("watch_synthetic_101")
    assert current is not None
    preview = store.preview_subscription(
        replace(current, consent_revision=2, lifecycle="paused"),
        authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1], authenticated_owner_chat_id=OWNER_TUPLE[2], now=NOW,
    )
    assert preview is not None
    entered, release, revision_done = Event(), Event(), Event()
    outcomes: list[str] = []
    revisions: list[WatchSubscription | None] = []

    def sender(_text: str) -> str:
        entered.set()
        assert release.wait(timeout=2)
        return "receipt_terminal_pause_001"

    delivery = Thread(target=lambda: outcomes.append(store.deliver_claimed_job(
        leased, _delivery_access(_delivery_registry()), sender=sender, now=NOW,
    )))
    delivery.start()
    assert entered.wait(timeout=2)

    def confirm_pause() -> None:
        revisions.append(store.confirm_subscription(
            preview.confirmation_ref,
            authenticated_chat_id=OWNER_TUPLE[0], authenticated_actor_id=OWNER_TUPLE[1],
            authenticated_owner_chat_id=OWNER_TUPLE[2], now=NOW,
        ))
        revision_done.set()

    reviser = Thread(target=confirm_pause)
    reviser.start()
    assert not revision_done.wait(timeout=0.1)
    release.set()
    delivery.join(timeout=3); reviser.join(timeout=3)
    assert not delivery.is_alive() and not reviser.is_alive()
    assert outcomes == ["sent"] and revisions and revisions[0] is not None
    assert store.job_state(queued.job_key) == "sent"
    assert store.subscription("watch_synthetic_101").lifecycle == "paused"  # type: ignore[union-attr]


def test_runner_rechecks_revocation_and_pause_after_preflight_before_sender(tmp_path) -> None:
    store = WatchJobStore(tmp_path / "terminal-recheck.db")
    _queued(store)
    registry = _delivery_registry()
    original_prepare = store.prepare_delivery

    def prepare_then_revoke(*args, **kwargs):
        prepared = original_prepare(*args, **kwargs)
        registry.revoke_grant("grant_watch_delivery_101", revoked_at=NOW)
        return prepared

    store.prepare_delivery = prepare_then_revoke  # type: ignore[method-assign]
    outcome = store.run_once(
        access_for_job=lambda _job: _delivery_access(registry),
        sender=lambda _text: (_ for _ in ()).throw(AssertionError("revoked grant must block sender")),
        now=NOW,
    )
    assert outcome.claimed == outcome.blocked == 1 and outcome.sent == 0

    paused = WatchJobStore(tmp_path / "terminal-pause.db")
    _queued(paused)
    registry = _delivery_registry()
    original_prepare = paused.prepare_delivery

    def prepare_then_pause(*args, **kwargs):
        prepared = original_prepare(*args, **kwargs)
        current = paused.subscription("watch_synthetic_101")
        assert current is not None
        assert _revise(paused, replace(current, consent_revision=2, lifecycle="paused"))
        return prepared

    paused.prepare_delivery = prepare_then_pause  # type: ignore[method-assign]
    outcome = paused.run_once(
        access_for_job=lambda _job: _delivery_access(registry),
        sender=lambda _text: (_ for _ in ()).throw(AssertionError("paused watch must block sender")),
        now=NOW,
    )
    assert outcome.claimed == outcome.blocked == 1 and outcome.sent == 0
