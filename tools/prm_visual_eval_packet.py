#!/usr/bin/env python3
"""Create privacy-safe Telegram-like visual UX packets from PRM product fixtures.

This tool never contacts Telegram, a provider, or a live UTD source. It reuses
the synthetic corpus in ``prm_product_ux_eval`` and writes reviewable HTML/PDF
screens plus a redacted judge manifest under an explicitly selected output dir.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import prm_product_ux_eval as product_ux


SCHEMA_VERSION = "prm_visual_eval_packet.v1"
DEFAULT_OUTPUT = ROOT / ".playbook-artifacts" / "prm_visual_eval"
SURFACE_ORDER = (
    "prm_application",
    "utd_ask",
    "utd_onboarding",
    "utd_profile_action",
    "utd_notification",
    "utd_feedback",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cases-per-surface", type=int, default=6)
    parser.add_argument("--pdf", action="store_true", help="Also write local PDF previews through WeasyPrint.")
    return parser


def select_cases(*, cases_per_surface: int) -> list[dict[str, Any]]:
    """Choose a balanced, stable visual review slice from the larger corpus."""
    corpus = product_ux.build_corpus()
    indexed = product_ux.build_case_index(
        corpus, include_one_turn_cases=True, dialogue_window_turns=4
    )
    selected: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for surface in SURFACE_ORDER:
        matches = [
            dict(case)
            for case in indexed
            if any(str(turn.get("surface") or "") == surface for turn in case.get("turns") or [])
        ]
        # Prefer a multi-turn slice where it exists: visual judgement needs
        # context as well as one attractive isolated bubble.
        matches.sort(
            key=lambda case: (
                not any(bool(turn.get("visual_priority")) for turn in case.get("turns") or [] if isinstance(turn, Mapping)),
                case.get("case_type") != "dialogue_window",
                str(case.get("case_id") or ""),
            )
        )
        chosen = 0
        for case in matches:
            case_id = str(case.get("case_id") or "")
            if not case_id or case_id in used_ids:
                continue
            selected.append(case)
            used_ids.add(case_id)
            chosen += 1
            if chosen >= max(1, cases_per_surface):
                break
    return selected


def render_case_html(case: Mapping[str, Any]) -> str:
    turns = case.get("turns") if isinstance(case.get("turns"), Sequence) else []
    bubbles: list[str] = []
    for turn in turns:
        if not isinstance(turn, Mapping):
            continue
        user = escape(str(turn.get("user_message") or ""))
        assistant = escape(str(turn.get("assistant_visible_message") or "")).replace("\n", "<br>")
        checks = turn.get("deterministic_checks") if isinstance(turn.get("deterministic_checks"), Mapping) else {}
        failed = [name for name, passed in checks.items() if passed is False]
        status = "PASS" if not failed else "CHECK: " + ", ".join(failed)
        bubbles.extend(
            [
                f'<div class="bubble user">{user}</div>',
                f'<div class="bubble assistant">{assistant}</div>',
                f'<div class="status">{escape(status)}</div>',
            ]
        )
    case_id = escape(str(case.get("case_id") or ""))
    return f"""<!doctype html>
<html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{case_id}</title><style>
*{{box-sizing:border-box}} body{{margin:0;background:#d9e4ee;font:15px/1.42 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#182533}}
.phone{{width:390px;min-height:740px;margin:24px auto;background:#e8f0f5;border:1px solid #b9c8d3;border-radius:24px;box-shadow:0 12px 30px #6b7a8850;overflow:hidden}}
.bar{{background:#527da2;color:#fff;padding:17px 20px;font-weight:650}} .meta{{padding:10px 18px;color:#5c6c78;font-size:12px}}
.chat{{padding:8px 14px 22px;display:flex;flex-direction:column;gap:8px}} .bubble{{max-width:87%;padding:10px 12px;border-radius:15px;overflow-wrap:anywhere}}
.user{{align-self:flex-end;background:#d5f1c3;border-bottom-right-radius:4px}} .assistant{{align-self:flex-start;background:#fff;border-bottom-left-radius:4px;box-shadow:0 1px 2px #72839230}}
.status{{align-self:center;color:#567163;font-size:11px;padding:2px 8px;background:#edf5ee;border-radius:8px}} @media(max-width:430px){{.phone{{width:100%;margin:0;border-radius:0;min-height:100vh}}}}
</style><body><main class="phone"><div class="bar">Personal Research Assistant</div><div class="meta">Synthetic fixture · {case_id}</div><section class="chat">{''.join(bubbles)}</section></main></body></html>"""


def write_packet(output_dir: Path, *, cases_per_surface: int, write_pdf: bool) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    screens_dir = output_dir / "screens"
    screens_dir.mkdir(exist_ok=True)
    selected = select_cases(cases_per_surface=cases_per_surface)
    pdf_error: str | None = None
    # The existing simulator resolves Settings from the environment. Point it at
    # a unique empty disposable database so this packet cannot read the real
    # operator archive even when AGENT_DB_PATH is configured on the host.
    previous_db = os.environ.get("AGENT_DB_PATH")
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="prm-visual-eval-") as temp_dir:
        os.environ["AGENT_DB_PATH"] = str(Path(temp_dir) / "synthetic.db")
        try:
            assistant_cache: dict[str, Any] = {}
            for index, spec in enumerate(selected, start=1):
                case = product_ux.simulate_judge_case(spec, assistant_cache=assistant_cache)
                stem = f"{index:02d}-{_safe_stem(str(case.get('case_id') or 'case'))}"
                html_path = screens_dir / f"{stem}.html"
                html_path.write_text(render_case_html(case), encoding="utf-8")
                row = {
                    "case_id": case.get("case_id"),
                    "case_type": case.get("case_type"),
                    "surfaces": sorted({str(turn.get("actual", {}).get("surface") or "") for turn in case.get("turns") or [] if isinstance(turn, Mapping)}),
                    "screen_html": str(html_path.relative_to(output_dir)),
                    "deterministic_summary": case.get("deterministic_summary"),
                    "judge_case": case,
                }
                if write_pdf and pdf_error is None:
                    pdf_path = html_path.with_suffix(".pdf")
                    try:
                        _write_pdf(html_path, pdf_path)
                    except RuntimeError as exc:
                        # HTML remains the portable visual artifact. A broken
                        # optional PDF backend must not discard a review packet.
                        pdf_error = str(exc)
                        pdf_path.unlink(missing_ok=True)
                    else:
                        row["screen_pdf"] = str(pdf_path.relative_to(output_dir))
                rows.append(row)
        finally:
            if previous_db is None:
                os.environ.pop("AGENT_DB_PATH", None)
            else:
                os.environ["AGENT_DB_PATH"] = previous_db
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "privacy": "synthetic fixtures only; an empty disposable AGENT_DB_PATH was used; do not add archive exports, tokens, chat IDs or live output",
        "judge_status": "not_run_advisory_only",
        "screenshots": "HTML previews are generated locally. PDF is optional and its local backend status is recorded below. PNG capture requires a separately installed local browser/rasterizer.",
        "pdf_status": "not_requested" if not write_pdf else ("unavailable" if pdf_error else "generated"),
        "pdf_error": pdf_error,
        "case_count": len(rows),
        "cases": rows,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output_dir / "judge_cases.ndjson").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row["judge_case"], ensure_ascii=False, sort_keys=True) + "\n")
    return manifest


def _write_pdf(html_path: Path, pdf_path: Path) -> None:
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover - dependency boundary
        raise RuntimeError("--pdf requires the local WeasyPrint dependency") from exc
    try:
        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
    except Exception as exc:  # pragma: no cover - backend/version boundary
        raise RuntimeError(f"local PDF preview backend failed: {exc}") from exc


def _safe_stem(value: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in value.lower()).strip("-")[:80] or "case"


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = write_packet(args.output_dir, cases_per_surface=args.cases_per_surface, write_pdf=args.pdf)
    print(json.dumps({"status": "ok", "output_dir": str(args.output_dir), "case_count": manifest["case_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
