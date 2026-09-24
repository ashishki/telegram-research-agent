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
    editorial = sub.add_parser(
        "editorial-brief",
        help="Operator-run brief with model editorial (default off).",
    )
    editorial.add_argument("question")
    editorial.add_argument("--out-dir", default=".playbook-artifacts/editorial_brief")
    editorial.add_argument("--model", default="")
    editorial.add_argument(
        "--consent",
        default="",
        help="Must be the exact literal 'enable-opencode-editorial'.",
    )
    return parser


def _run_editorial_brief(args: argparse.Namespace, settings) -> int:
    """Default-off operator path: archive -> model editorial -> paginated PDF."""

    from pathlib import Path

    from prm.application import _brief_request_from_archive_payload
    from prm.briefs import build_brief_document
    from prm.editorial_transport import (
        build_operator_editorial_access,
        editorial_enabled,
        synthesize_opencode_editorial,
    )
    from prm import report_exports
    from prm.contracts import OperatorRequest

    if not editorial_enabled():
        print("Editorial provider is disabled. Set PRM_EDITORIAL_OPENCODE_ENABLED=1 and pass --consent.")
        return 1
    assistant = PersonalResearchAssistant(settings=settings)
    request = OperatorRequest(query=str(args.question), mode="brief", chat_id="local-editorial-cli")
    result = assistant.answer(request)
    payload = result.payload or {}
    if not payload.get("brief_document"):
        print(f"No brief document: {result.status}")
        return 1
    document = build_brief_document(
        _brief_request_from_archive_payload(request=request, payload=payload, topic=str(args.question))
    )
    access = build_operator_editorial_access(
        owner_ref="owner_editorial_cli",
        connection_ref="connection_editorial_cli",
        resource_ref="resource_editorial_cli",
        consent=str(args.consent or ""),
    )
    editorial, measurement = synthesize_opencode_editorial(
        document, question=str(args.question), access=access, model=str(args.model or "") or None
    )
    if editorial is not None:
        from dataclasses import replace

        document = build_brief_document(
            replace(
                _brief_request_from_archive_payload(request=request, payload=payload, topic=str(args.question)),
                editorial=editorial,
            )
        )
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "brief_paginated.html").write_text(str(report_exports.render_paginated_html(document).body), encoding="utf-8")
    (out / "brief_paginated.pdf").write_bytes(report_exports.render_paginated_pdf(document).body)
    print(f"editorial={measurement.get('status')} stories={len(document.editorial.stories) if document.editorial else 0}")
    print(f"wrote {out / 'brief_paginated.pdf'}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    if args.command == "assistant":
        run_bot(settings, runtime_mode=BOT_RUNTIME_PRM_ASSISTANT)
        return 0
    if args.command == "editorial-brief":
        return _run_editorial_brief(args, settings)
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
