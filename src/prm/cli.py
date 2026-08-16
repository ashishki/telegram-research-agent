"""Compact CLI for the active PRM product surface."""

from __future__ import annotations

import argparse
from typing import Sequence

from bot.bot import run_bot
from bot.runtime import BOT_RUNTIME_PRM_ASSISTANT
from config.settings import load_settings
from prm.application import PersonalResearchAssistant
from prm.contracts import OperatorRequest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prm", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("assistant", help="Run the private Telegram PRM assistant.")
    for name in ("research", "brief", "chat"):
        command = sub.add_parser(name, help=f"Run one {name} request.")
        command.add_argument("question")
        command.add_argument("--project", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    if args.command == "assistant":
        run_bot(settings, runtime_mode=BOT_RUNTIME_PRM_ASSISTANT)
        return 0
    assistant = PersonalResearchAssistant(settings=settings)
    result = assistant.answer(
        OperatorRequest(
            query=str(args.question),
            mode=str(args.command),  # type: ignore[arg-type]
            project_name=str(args.project or ""),
        )
    )
    print(result.text)
    return 0 if result.status not in {"invalid", "error"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
