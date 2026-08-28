#!/usr/bin/env python3
"""Score all external-watch scenarios with the proposed deterministic policy.

These are policy proposals, never human/gold labels.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

OUTCOME = {
    "cancelled":"notify", "reinstated":"notify", "date_change":"notify", "location_change":"notify", "deadline_change":"notify",
    "duplicate":"ignore", "cosmetic_change":"ignore", "stale":"ignore", "prompt_injection":"ignore", "past_event":"ignore", "unsupported_savings":"ignore",
}


def proposed_outcome(scenario: str) -> str:
    return OUTCOME.get(scenario, "ambiguous")


def score_manifest(payload: dict) -> dict:
    rows=[]
    counts={"notify":0,"ignore":0,"ambiguous":0}
    for case in payload.get("cases") or []:
        outcome=proposed_outcome(str(case.get("scenario") or ""))
        counts[outcome]+=1
        rows.append({"id":case.get("id"),"split":case.get("split"),"scenario":case.get("scenario"),"proposed_outcome":outcome,"human_label":None})
    return {"schema_version":"utd_policy_eval.v1","case_count":len(rows),"counts":counts,"human_labels_added":False,"holdouts_used_for_tuning":False,"rows":rows}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args=parser.parse_args()
    payload=json.loads(args.manifest.read_text(encoding="utf-8"))
    print(json.dumps(score_manifest(payload), ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == "__main__": raise SystemExit(main())
