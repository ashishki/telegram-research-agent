#!/usr/bin/env python3
"""Run repository test tiers without invoking the prohibited full suite."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

PRM_ACTIVE_TESTS = (
    "tests/test_archive_documents.py",
    "tests/test_archive_search.py",
    "tests/test_archive_vector.py",
    "tests/test_archive_api_vector.py",
    "tests/test_operator_context.py",
    "tests/test_memory_research.py",
    "tests/test_evidence_quality.py",
    "tests/test_claim_ledger.py",
    "tests/test_primary_source_verification.py",
    "tests/test_project_context.py",
    "tests/test_rag_context_pack.py",
    "tests/test_linked_sources.py",
    "tests/test_reaction_fast_lane.py",
    "tests/test_prm_post_answer_actions.py",
    "tests/test_prm_qa_dataset_eval.py",
    "tests/test_callbacks.py",
    "tests/test_prm_application.py",
    "tests/test_prm_bot_dispatch.py",
    "tests/test_prm_cli.py",
    "tests/test_retrofit_boundaries.py",
    "tests/test_prm_intent_archive_contract.py",
    "tests/test_prm_replay_query.py",
    "tests/test_prm_qa_usage_recap.py",
)

LEGACY_COMPAT_TESTS = (
    "tests/test_prm_live_ux_eval.py",
    "tests/test_weekly_brief_v3.py",
    "tests/test_knowledge_library.py",
    "tests/test_prm_release_gate.py",
    "tests/test_workflow_telemetry.py",
    "tests/test_semantic_retrieval.py",
)

RETROFIT_TESTS = (
    "tests/test_prm_application.py",
    "tests/test_prm_bot_dispatch.py",
    "tests/test_prm_cli.py",
    "tests/test_retrofit_boundaries.py",
    "tests/test_prm_intent_archive_contract.py",
)

FAST_CONTRACT_TESTS = (
    "tests/test_core_boundaries.py",
    "tests/test_delivery_health.py",
    "tests/test_cost_stats.py",
    "tests/test_llm_client.py",
    "tests/test_router.py",
    "tests/test_retrieval.py",
    "tests/test_week_bounds.py",
    "tests/test_pi_intent.py",
    "tests/test_callbacks.py",
    *PRM_ACTIVE_TESTS,
)

PYTEST = (sys.executable, "-m", "pytest")
PLAYBOOK_VALIDATOR = (
    sys.executable,
    "tools/playbook_validate.py",
    "--root",
    ".",
    "--check",
    "tasks",
    "--check",
    "references",
)


@dataclass(frozen=True)
class TierCommand:
    argv: tuple[str, ...]
    env: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class TestTier:
    name: str
    description: str
    commands: tuple[TierCommand, ...]


TEST_TIERS = {
    "focused-prm": TestTier(
        "focused-prm",
        "Active PRM request-to-answer, safety, intent-contract and retrofit tests.",
        (TierCommand((*PYTEST, *PRM_ACTIVE_TESTS, "-q"), env=(("PYTHONPATH", "src"),)),),
    ),
    "retrofit-boundaries": TestTier(
        "retrofit-boundaries",
        "Fast structural checks for application, bot and CLI boundaries.",
        (TierCommand((*PYTEST, *RETROFIT_TESTS, "-q"), env=(("PYTHONPATH", "src"),)),),
    ),
    "legacy-compat": TestTier(
        "legacy-compat",
        "Explicit report-era and superseded evaluator compatibility tests.",
        (TierCommand((*PYTEST, *LEGACY_COMPAT_TESTS, "-q"), env=(("PYTHONPATH", "src"),)),),
    ),
    "fast-contract": TestTier(
        "fast-contract",
        "Deterministic active contract subset.",
        (TierCommand((*PYTEST, *FAST_CONTRACT_TESTS, "-q"), env=(("PYTHONPATH", "src"),)),),
    ),
    "ops-date-sensitive": TestTier(
        "ops-date-sensitive",
        "Date-sensitive operations test isolated from fast loops.",
        (TierCommand((*PYTEST, "tests/test_product_ops.py", "-q"), env=(("PYTHONPATH", "src"),)),),
    ),
    "block-review": TestTier(
        "block-review",
        "Playbook and whitespace checks.",
        (TierCommand(PLAYBOOK_VALIDATOR), TierCommand(("git", "diff", "--check"))),
    ),
    "full": TestTier("full", "Prohibited complete suite.", ()),
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def display_command(command: TierCommand) -> str:
    prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in command.env)
    return f"{prefix} {shlex.join(command.argv)}".strip()


def _run(command: TierCommand) -> int:
    env = os.environ.copy()
    for key, value in command.env:
        env[key] = f"{value}{os.pathsep}{env[key]}" if key == "PYTHONPATH" and env.get(key) else value
    print(f"$ {display_command(command)}", flush=True)
    return subprocess.run(command.argv, cwd=_repo_root(), env=env, check=False).returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tier", nargs="?", choices=sorted(TEST_TIERS))
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--print-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        for tier in TEST_TIERS.values():
            print(f"{tier.name}: {tier.description}")
        return 0
    if not args.tier:
        build_parser().error("tier is required unless --list is used")
    if args.tier == "full":
        print("full test tier is prohibited; use a focused tier", file=sys.stderr)
        return 2
    for command in TEST_TIERS[args.tier].commands:
        if args.print_only:
            print(display_command(command))
            continue
        code = _run(command)
        if code:
            return int(code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
