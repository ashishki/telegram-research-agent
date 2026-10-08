#!/usr/bin/env python3
"""Publish a complete design record only from all independent phase reviews."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import uuid
import re
import opencode_role_review as review
from opencode_role_review import ROOT, ROLES, REVIEW_GROUPS, SPEC_GROUPS, ReviewBlocked, digest, pinned_modules


def finalize(root: Path, feature: str, role: str, results: list[Path]):
    root = root.resolve()
    lib, workflow, approval = pinned_modules(root)
    registry_path = root / f"docs/design/{feature}.design.json"
    design = json.loads(registry_path.read_text())
    current_hashes = lib.design_hashes(root, design)
    head = workflow.git_commit(root)
    by_group = {}
    for path in results:
        path = path.resolve()
        if not path.is_relative_to(root / ".playbook-artifacts/opencode-runs"):
            raise ReviewBlocked("phase result must come from an immutable local OpenCode run")
        raw = path.read_bytes()
        if path.with_suffix(".json.sha256").read_text().strip() != digest(raw):
            raise ReviewBlocked("phase result hash changed")
        result = json.loads(raw)
        group = result.get("slice_group")
        if group not in REVIEW_GROUPS or group in by_group:
            raise ReviewBlocked("missing, unknown or duplicate review phase")
        if (result.get("feature_id") != feature or result.get("role") != role
            or result.get('schema_version')!='assistant.opencode_design_review.v1' or result.get('review_scope')!='complete_design'
            or result.get("provider") != "opencode_go" or result.get("read_only") is not True
            or result.get("requested_model") != "mimo-v2.6-pro"
            or result.get("observed_model") != "mimo-v2.6-pro"):
            raise ReviewBlocked("phase reviewer identity/scope mismatch")
        if result.get("reviewed_head") != head or result.get("design_hashes") != current_hashes:
            raise ReviewBlocked("phase reviewed a different HEAD or design")
        if set(result.get("reviewed_slice_ids", [])) != {f"PAI-{n:02}" for n in REVIEW_GROUPS[group]}:
            raise ReviewBlocked("phase slice coverage incomplete")
        if set(result.get("reviewed_spec_sections", [])) != SPEC_GROUPS[group]:
            raise ReviewBlocked("phase specification coverage incomplete")
        for item in result["documents"]:
            doc = lib.safe_repo_path(root, item["path"])
            if doc is None or digest(doc.read_bytes()) != item["sha256"]:
                raise ReviewBlocked("phase context changed")
        report = path.parent / "report.md"
        if digest(report.read_bytes()) != result["report_sha256"]:
            raise ReviewBlocked("phase report hash changed")
        if json.loads((path.parent/'input_manifest.json').read_text())!=result['documents']:
            raise ReviewBlocked('phase input manifest differs')
        if digest((path.parent/'input_packet.txt').read_bytes())!=result['input_sha256']:
            raise ReviewBlocked('phase input packet changed')
        markers=re.findall(r'^'+ROLES[role]+r':\s*(PASS|ADVISORY|STOP_SHIP)\s*$',report.read_text(),re.M)
        if markers!=[result['verdict']]:raise ReviewBlocked('phase report marker differs')
        body='{'+report.read_text().split('\n{',1)[1]
        parsed=review.parse_response({'model':result['observed_model'],'choices':[{'finish_reason':'stop','message':{'content':body}}]},result['requested_model'])
        if parsed['verdict']!=result['verdict']:raise ReviewBlocked('phase structured verdict differs')
        if result["verdict"] not in {"PASS", "ADVISORY", "STOP_SHIP"}:
            raise ReviewBlocked("phase has no valid verdict")
        by_group[group] = (result, path, report)
    if set(by_group) != set(REVIEW_GROUPS):
        raise ReviewBlocked("all four independent review phases are required")
    slices = {sid for result, _, _ in by_group.values() for sid in result["reviewed_slice_ids"]}
    sections = {sid for result, _, _ in by_group.values() for sid in result["reviewed_spec_sections"]}
    if slices != {s["slice_id"] for s in design["slices"]} or sections != set(range(16)):
        raise ReviewBlocked("whole programme/spec coverage incomplete")
    tooling_audit_ref = review.require_tooling_audit(root)
    if any(result.get("tooling_audit_ref") != tooling_audit_ref for result, _, _ in by_group.values()):
        raise ReviewBlocked("phase receipts require current independently audited tooling")
    verdicts = {r["verdict"] for r, _, _ in by_group.values()}
    verdict = "STOP_SHIP" if "STOP_SHIP" in verdicts else "ADVISORY" if "ADVISORY" in verdicts else "PASS"
    run_dir = root / ".playbook-artifacts/opencode-complete" / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version":"assistant.opencode_complete_review.v1","role":role,
                "feature_id":feature,"reviewed_head":head,"design_hashes":current_hashes,
                "verdict":verdict,"tooling_audit_ref":tooling_audit_ref,
                "coverage":{"slices":sorted(slices),"spec_sections":sorted(sections)},
                "parts":[{"group":g,"result":p.relative_to(root).as_posix(),"sha256":digest(p.read_bytes()),
                          "verdict":r["verdict"]} for g,(r,p,_) in by_group.items()]}
    output = run_dir / "result.json"
    output.write_text(json.dumps(manifest, indent=2)+"\n")
    report = run_dir / "report.md"
    report.write_text(f"# Complete independent OpenCode design review\n\n{ROLES[role]}: {verdict}\n\n"
                      "This is deterministic aggregation of four actual independent reviews; no implementer verdict.\n"
                      + "\n".join(f"\n## {g}\n\n"+re.sub(r"^"+ROLES[role]+r":", "Phase verdict:", rp.read_text(), flags=re.M)
                                  for g,(_,_,rp) in by_group.items()))
    approval.write_design_review_record(root=root,feature_id=feature,role=role,
        report_path=report.relative_to(root).as_posix(),reviewed_design=design,
        reviewer_binding="opencode_go_complete:"+output.relative_to(root).as_posix(),read_only=True)
    print(json.dumps({"status":"complete_review_record_written","verdict":verdict,"result":str(output)}))
    return 1 if verdict=="STOP_SHIP" else 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--feature-id",required=True)
    parser.add_argument("--role",choices=sorted(ROLES),required=True)
    parser.add_argument("--result",type=Path,action="append",required=True)
    args=parser.parse_args()
    try:return finalize(args.root,args.feature_id,args.role,args.result)
    except Exception as exc:
        print("Complete review blocked: "+(str(exc) if isinstance(exc,ReviewBlocked) else type(exc).__name__))
        return 2

if __name__=="__main__":raise SystemExit(main())
