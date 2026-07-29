#!/usr/bin/env python3
"""Run or print repository test tiers for focused PRM work and block review."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


PRM_TESTS = (
    "tests/test_archive_documents.py",
    "tests/test_archive_search.py",
    "tests/test_pi_tools.py",
    "tests/test_pi_chat.py",
    "tests/test_project_context.py",
    "tests/test_learning_layer.py",
    "tests/test_weekly_brief_v3.py",
    "tests/test_workflow_telemetry.py",
    "tests/test_prm_release_gate.py",
    "tests/test_reaction_fast_lane.py",
    "tests/test_selective_enrichment.py",
    "tests/test_archive_retrieval_eval.py",
    "tests/test_knowledge_library.py",
)

FAST_CONTRACT_TESTS = (
    "tests/test_core_boundaries.py",
    "tests/test_delivery_health.py",
    "tests/test_cost_stats.py",
    "tests/test_llm_client.py",
    "tests/test_router.py",
    "tests/test_retrieval.py",
    "tests/test_semantic_retrieval.py",
    "tests/test_week_bounds.py",
    "tests/test_pi_intent.py",
    "tests/test_cli.py",
    "tests/test_handlers.py",
    "tests/test_callbacks.py",
    *PRM_TESTS,
)

PYTEST_QUIET = (sys.executable, "-m", "pytest")
PLAYBOOK_VALIDATOR = (
    sys.executable,
    "tools/playbook_validate.py",
    "--root",
    ".",
    "--check",
    "tasks",
    "--check",
    "placeholders",
    "--check",
    "readiness",
    "--check",
    "delivery",
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


TEST_TIERS: dict[str, TestTier] = {
    "focused-prm": TestTier(
        name="focused-prm",
        description="Focused PRM RAG/assistant tests for current retrofit work.",
        commands=(TierCommand((*PYTEST_QUIET, *PRM_TESTS, "-q"), env=(("PYTHONPATH", "src"),)),),
    ),
    "fast-contract": TestTier(
        name="fast-contract",
        description="Fast deterministic contract/unit subset excluding date-sensitive ops.",
        commands=(TierCommand((*PYTEST_QUIET, *FAST_CONTRACT_TESTS, "-q"), env=(("PYTHONPATH", "src"),)),),
    ),
    "ops-date-sensitive": TestTier(
        name="ops-date-sensitive",
        description="Known date-sensitive ops validation test isolated from fast loops.",
        commands=(TierCommand((*PYTEST_QUIET, "tests/test_product_ops.py", "-q"), env=(("PYTHONPATH", "src"),)),),
    ),
    "full": TestTier(
        name="full",
        description="Complete pytest suite; currently expected to expose one known product_ops date-sensitive failure.",
        commands=(TierCommand((*PYTEST_QUIET, "tests/", "-q"), env=(("PYTHONPATH", "src"),)),),
    ),
    "block-review": TestTier(
        name="block-review",
        description="Block-review gate: playbook validator, full suite, and whitespace diff check.",
        commands=(
            TierCommand(PLAYBOOK_VALIDATOR),
            TierCommand((*PYTEST_QUIET, "tests/", "-q"), env=(("PYTHONPATH", "src"),)),
            TierCommand(("git", "diff", "--check")),
        ),
    ),
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def display_command(command: TierCommand) -> str:
    env_prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in command.env)
    rendered = shlex.join(command.argv)
    return f"{env_prefix} {rendered}".strip()


def _run_command(command: TierCommand, *, root: Path) -> int:
    env = os.environ.copy()
    for key, value in command.env:
        if key == "PYTHONPATH" and env.get(key):
            env[key] = f"{value}{os.pathsep}{env[key]}"
        else:
            env[key] = value
    print(f"$ {display_command(command)}", flush=True)
    result = subprocess.run(command.argv, cwd=root, env=env, check=False)
    return int(result.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tier", nargs="?", choices=sorted(TEST_TIERS))
    parser.add_argument("--list", action="store_true", help="List available tiers.")
    parser.add_argument("--print-only", action="store_true", help="Print tier commands without executing them.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        for tier in TEST_TIERS.values():
            print(f"{tier.name}: {tier.description}")
        return 0
    if not args.tier:
        build_parser().error("tier is required unless --list is used")
    tier = TEST_TIERS[args.tier]
    for command in tier.commands:
        if args.print_only:
            print(display_command(command))
            continue
        return_code = _run_command(command, root=_repo_root())
        if return_code != 0:
            return return_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
