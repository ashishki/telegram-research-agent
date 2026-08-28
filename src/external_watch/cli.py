"""CLI for one-shot UTD shadow collection."""
from __future__ import annotations

import argparse
import json
import os
from .collector import ShadowCollector
from .delivery import default_sidecar_db


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prm-db", default=os.environ.get("PRM_DB_PATH", "data/agent.db"))
    parser.add_argument("--sidecar-db", default=default_sidecar_db())
    parser.add_argument("--enable-shadow", action="store_true")
    args = parser.parse_args()
    result = ShadowCollector(prm_db=args.prm_db, sidecar_db=args.sidecar_db, enabled=args.enable_shadow).run_once()
    print(json.dumps({
        "enabled": result.enabled,
        "profile_loaded": result.profile_loaded,
        "source_status": dict(result.source_status),
        "change_count": len(result.changes),
        "relevant_change_count": sum(bool(x.get("relevance", {}).get("relevant")) for x in result.changes),
        "candidate_count": len(result.candidates),
        "urgent_candidate_count": sum(bool(x.get("relevance", {}).get("urgent")) for x in result.candidates),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
