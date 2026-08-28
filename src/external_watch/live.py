"""One-shot collection + optional delivery harness for UTD watch."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from .collector import ShadowCollector
from .delivery import DeliveryStore, deliver_candidates


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prm-db", required=True)
    p.add_argument("--sidecar-db", required=True)
    p.add_argument("--enable-shadow", action="store_true")
    p.add_argument("--enable-delivery", action="store_true", help="Still requires UTD_WATCH_DELIVERY_ENABLED=1")
    p.add_argument("--feedback-summary", action="store_true")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sidecar = Path(args.sidecar_db)
    if args.feedback_summary:
        print(json.dumps(DeliveryStore(sidecar).feedback_summary(), ensure_ascii=False, sort_keys=True))
        return 0
    run = ShadowCollector(prm_db=args.prm_db, sidecar_db=sidecar, enabled=args.enable_shadow).run_once()
    delivery = deliver_candidates(
        run.candidates,
        sidecar_db=sidecar,
        token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        chat_id=os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip(),
        explicit_enable=args.enable_delivery,
    )
    print(json.dumps({
        "shadow_enabled": run.enabled,
        "profile_loaded": run.profile_loaded,
        "change_count": len(run.changes),
        "candidate_count": len(run.candidates),
        "source_status": dict(run.source_status),
        "delivery": delivery,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
