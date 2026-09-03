"""One-shot collection + optional delivery harness for UTD watch."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Sequence

from .calibration import calibration_report
from .collector import ShadowCollector
from .delivery import DeliveryStore, default_sidecar_db, deliver_candidates


def _default_prm_db() -> str:
    return os.environ.get("AGENT_DB_PATH", "").strip() or "data/agent.db"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prm-db", default=_default_prm_db())
    p.add_argument("--sidecar-db", default=default_sidecar_db())
    p.add_argument("--enable-shadow", action="store_true")
    p.add_argument("--enable-delivery", action="store_true", help="Still requires UTD_WATCH_DELIVERY_ENABLED=1")
    p.add_argument("--feedback-summary", action="store_true")
    p.add_argument("--calibration-report", action="store_true")
    p.add_argument("--show-candidates", action="store_true")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sidecar = Path(args.sidecar_db)
    if args.feedback_summary:
        print(json.dumps(DeliveryStore(sidecar).feedback_summary(), ensure_ascii=False, sort_keys=True))
        return 0
    if args.calibration_report:
        print(json.dumps(calibration_report(sidecar), ensure_ascii=False, sort_keys=True))
        return 0
    if not args.prm_db:
        print(
            json.dumps(
                {"status": "failed_closed", "reason": "missing_prm_db"},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    run = ShadowCollector(prm_db=args.prm_db, sidecar_db=sidecar, enabled=args.enable_shadow).run_once()
    delivery = deliver_candidates(
        run.candidates,
        sidecar_db=sidecar,
        token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        chat_id=os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip(),
        explicit_enable=args.enable_delivery,
    )
    output = {
        "shadow_enabled": run.enabled,
        "profile_loaded": run.profile_loaded,
        "change_count": len(run.changes),
        "candidate_count": len(run.candidates),
        "source_status": dict(run.source_status),
        "delivery": delivery,
    }
    if args.show_candidates:
        output["candidates"] = [
            {
                "source": candidate.get("source"),
                "item_key": candidate.get("item_key"),
                "change_type": candidate.get("change_type"),
                "title": (candidate.get("payload") or {}).get("title") if isinstance(candidate.get("payload"), dict) else "",
                "url": (candidate.get("payload") or {}).get("url") if isinstance(candidate.get("payload"), dict) else "",
                "relevance": candidate.get("relevance"),
            }
            for candidate in run.candidates
        ]
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
