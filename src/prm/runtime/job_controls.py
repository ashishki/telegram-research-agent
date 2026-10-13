"""Resolve a job from trusted owner references; ambiguity never selects a job."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class JobCandidate:
    job_ref: str
    title: str


@dataclass(frozen=True)
class ResolvedJobTarget:
    job_ref: str | None
    reason: str
    candidates: tuple[JobCandidate, ...] = ()
    has_more: bool = False


@dataclass(frozen=True)
class JobProgressView:
    status: str
    checkpoint: str | None
    has_result: bool
    cancellable: bool
    awaiting_reconciliation: bool


def resolve_job_target(queue, bindings, *, owner, destination, command, explicit_ref=None, reply_message_id=None):
    if explicit_ref is not None:
        return ResolvedJobTarget(explicit_ref, 'explicit')
    if reply_message_id is not None:
        binding = bindings.for_message(destination, reply_message_id)
        return ResolvedJobTarget(binding.job_ref if binding else None, 'reply' if binding else 'unknown_reply')
    rows = queue.control_candidates(owner=owner, command=command, limit=9)
    if len(rows) == 1: return ResolvedJobTarget(rows[0]['id'], 'only_active')
    candidates = tuple(JobCandidate(row['id'], row['title']) for row in rows[:8])
    return ResolvedJobTarget(None, 'ambiguous' if candidates else 'none', candidates, len(rows) > 8)


def progress_view(state):
    stage = state.get('checkpoint', {}).get('stage')
    # Only known persisted stages can become user-facing progress. Arbitrary
    # checkpoint/source strings never become a stage or a percentage.
    names = {'input_verified': 'Вход проверен', 'transcribed': 'Расшифровка готова',
             'answering': 'Готовлю ответ', 'reading': 'Читаю источники', 'gap_check': 'Проверяю покрытие'}
    effect_started = state.get('mode') == 'effect' and state['attempts'] > 0
    return JobProgressView(state['status'], names.get(stage) if isinstance(stage, str) else None, bool(state.get('result_ref')),
        state['status'] in {'queued', 'retry_wait', 'leased', 'running'} and not effect_started,
        state['status'] == 'awaiting_reconciliation' or effect_started or state.get('checkpoint', {}).get('outcome') == 'unknown')
