"""Ephemeral local process supervision for bounded research steps.

This is deliberately not a queue, daemon, scheduler, or persistence layer.
Every call creates short-lived child processes in memory and joins or kills
them before returning.  It exists because a Python thread cannot safely stop
an uncooperative provider callback once a research deadline or cancellation
has been reached.

The worker is Linux/fork-only by design.  A different platform returns a
default-deny outcome rather than falling back to a thread that could continue
egress after the caller received a partial result.
"""

from __future__ import annotations

from dataclasses import dataclass
import multiprocessing as mp
from multiprocessing.connection import Connection, wait
import sys
from time import monotonic
from typing import Any, Callable, Sequence


@dataclass(frozen=True, slots=True)
class SupervisedWork:
    """One caller-owned callback that is allowed to run in a child process.

    ``preflight`` is mandatory and runs in the parent only after the child has
    forked but before it receives its start signal.  It is the default-deny
    ingress seam used by PA-06 to consume a parent-side one-use capability
    reservation (or explicitly attest a local-only read). The child inherits
    the pre-consumption snapshot and can therefore validate the same sealed
    scope at the actual provider call without sharing an in-memory registry.
    """

    name: str
    callback: Callable[[], Any]
    fallback: Callable[[str], Any]
    preflight: Callable[[], Any | None]


def _child_main(connection: Connection, callback: Callable[[], Any]) -> None:
    """Wait for an explicit parent start signal, then return data or error."""

    try:
        if connection.recv() != "start":
            return
        connection.send(("ok", callback()))
    except Exception as exc:  # child failures are rendered as partial data
        try:
            connection.send(("error", type(exc).__name__))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        connection.close()


def run_supervised_work(
    work_items: Sequence[SupervisedWork],
    *,
    deadline_monotonic: float,
    cancelled: Callable[[], bool],
) -> list[Any]:
    """Return every bounded result, killing unfinished children before return.

    This function purposely does not provide a generic cross-platform worker
    abstraction.  On a non-Linux or non-fork runtime it returns an explicit
    no-execution result.  On Linux, callbacks cannot receive a start signal
    until parent-side preflight has succeeded.
    """

    if not work_items:
        return []
    if sys.platform != "linux":
        return [item.fallback("worker_unavailable") for item in work_items]
    try:
        context = mp.get_context("fork")
    except ValueError:
        return [item.fallback("worker_unavailable") for item in work_items]

    active: dict[Connection, tuple[SupervisedWork, mp.Process]] = {}
    results: list[Any] = []
    try:
        for item in work_items:
            if cancelled():
                results.append(item.fallback("cancelled_before_start"))
                continue
            if monotonic() >= deadline_monotonic:
                results.append(item.fallback("time_budget_exhausted"))
                continue
            parent, child = context.Pipe(duplex=True)
            process = context.Process(target=_child_main, args=(child, item.callback), daemon=True)
            try:
                process.start()
            except (OSError, RuntimeError):
                child.close()
                parent.close()
                results.append(item.fallback("worker_unavailable"))
                continue
            child.close()
            try:
                direct_result = item.preflight()
            except Exception:
                direct_result = item.fallback("authorization_required")
            if direct_result is not None:
                _stop_process(process)
                parent.close()
                results.append(direct_result)
                continue
            if cancelled():
                _stop_process(process)
                parent.close()
                results.append(item.fallback("cancelled_after_authorization"))
                continue
            if monotonic() >= deadline_monotonic:
                _stop_process(process)
                parent.close()
                results.append(item.fallback("deadline_after_authorization"))
                continue
            try:
                parent.send("start")
            except (BrokenPipeError, EOFError, OSError):
                _stop_process(process)
                parent.close()
                results.append(item.fallback("provider_failed"))
                continue
            active[parent] = (item, process)

        while active:
            status = _terminal_status(deadline_monotonic, cancelled)
            if status is not None:
                for connection, (item, process) in list(active.items()):
                    _stop_process(process)
                    connection.close()
                    results.append(item.fallback(status))
                    del active[connection]
                break
            ready = wait(tuple(active), timeout=min(0.05, max(0.0, deadline_monotonic - monotonic())))
            for connection in ready:
                item, process = active.pop(connection)
                try:
                    kind, payload = connection.recv()
                    if kind == "ok":
                        results.append(payload)
                    else:
                        results.append(item.fallback("provider_failed"))
                except (EOFError, OSError):
                    results.append(item.fallback("provider_failed"))
                finally:
                    connection.close()
                    process.join(timeout=0.05)
                    if process.is_alive():
                        _stop_process(process)
    finally:
        for connection, (_item, process) in active.items():
            _stop_process(process)
            connection.close()
    return results


def _terminal_status(deadline_monotonic: float, cancelled: Callable[[], bool]) -> str | None:
    if cancelled():
        return "cancelled_during_execution"
    if monotonic() >= deadline_monotonic:
        return "time_budget_exhausted"
    return None


def _stop_process(process: mp.Process) -> None:
    """Use SIGKILL where available so no callback remains alive after return."""

    if process.is_alive():
        try:
            process.kill()
        except (AttributeError, OSError):
            process.terminate()
    process.join(timeout=0.1)
    if process.is_alive():  # defensive fallback for an unusual runtime
        process.terminate()
        process.join(timeout=0.1)
