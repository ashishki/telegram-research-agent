#!/usr/bin/env python3
"""Shared deterministic helpers for Playbook RAG Evaluation v2 tools."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None  # type: ignore[assignment]


SCHEMA_VERSION_MANIFEST = "playbook.rag_eval_manifest.v1"
SCHEMA_VERSION_CASE = "playbook.rag_eval_case.v1"
SCHEMA_VERSION_OBSERVATION = "playbook.rag_eval_observation.v1"
SCHEMA_VERSION_RESULT = "playbook.rag_eval_result.v1"
SCHEMA_VERSION_COMPARISON = "playbook.rag_eval_comparison.v1"
SCORER_VERSION = "playbook-rag-eval-scorer-v1"


@dataclass(frozen=True)
class RagFinding:
    severity: str
    check_id: str
    message: str
    path: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "check_id": self.check_id,
            "message": self.message,
            "path": self.path,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(data: Any) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSONL record: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_no}: JSONL record must be an object")
        rows.append(value)
    return rows


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def schema_path(root: Path, name: str) -> Path:
    local = root / "schemas" / name
    if local.exists():
        return local
    return Path(__file__).resolve().parents[1] / "schemas" / name


def validate_schema(root: Path, schema_name: str, data: Any, artifact_path: Path) -> list[RagFinding]:
    if Draft202012Validator is None:
        return [RagFinding("error", "RAG_SCHEMA_VALIDATOR_MISSING", "jsonschema is required", str(artifact_path))]
    schema = load_json(schema_path(root, schema_name))
    validator = Draft202012Validator(schema)
    findings: list[RagFinding] = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
        field_path = ".".join(str(part) for part in error.path)
        suffix = f" at {field_path}" if field_path else ""
        findings.append(
            RagFinding(
                "error",
                "RAG_SCHEMA_INVALID",
                f"{schema_name}{suffix}: {error.message}",
                str(artifact_path),
            )
        )
    return findings


def safe_resolve(root: Path, raw_path: str) -> Path | None:
    path = Path(raw_path)
    if path.is_absolute() or ".." in path.parts or "\\" in raw_path:
        return None
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def artifact_ref(path: Path, root: Path, *, kind: str | None = None, artifact_id: str | None = None) -> dict[str, str]:
    ref: dict[str, str] = {
        "path": str(path.resolve().relative_to(root.resolve())),
        "sha256": sha256_file(path),
    }
    if kind:
        ref["kind"] = kind
    if artifact_id:
        ref["id"] = artifact_id
    return ref


def validate_ref(root: Path, ref: dict[str, Any], check_id: str, label: str) -> list[RagFinding]:
    raw_path = ref.get("path")
    expected_hash = ref.get("sha256")
    if not isinstance(raw_path, str) or not raw_path:
        return [RagFinding("error", check_id, f"{label} path is missing")]
    resolved = safe_resolve(root, raw_path)
    if resolved is None:
        return [RagFinding("error", "RAG_PATH_UNSAFE", f"{label} path escapes project root: {raw_path}", raw_path)]
    if not resolved.is_file():
        return [RagFinding("error", "RAG_ARTIFACT_MISSING", f"{label} artifact is missing", raw_path)]
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        return [RagFinding("error", "RAG_HASH_INVALID", f"{label} sha256 is invalid", raw_path)]
    actual = sha256_file(resolved)
    if actual != expected_hash:
        return [
            RagFinding(
                "error",
                "RAG_HASH_MISMATCH",
                f"{label} sha256 mismatch: expected {expected_hash}, actual {actual}",
                raw_path,
            )
        ]
    return []


def git_text(root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def current_commit(root: Path) -> str | None:
    value = git_text(root, ["rev-parse", "HEAD"])
    return value if len(value) == 40 else None


def current_dirty_state(root: Path) -> list[str]:
    value = git_text(root, ["status", "--short"])
    if not value:
        return []
    return [line for line in value.splitlines() if ".playbook-artifacts/" not in line]


def condition_fingerprint(condition: dict[str, Any]) -> str:
    stable = {key: value for key, value in condition.items() if key != "compatibility_fingerprint"}
    return sha256_json(stable)


def config_fingerprint(manifest: dict[str, Any], condition_id: str) -> str:
    condition = get_condition(manifest, condition_id)
    stable = {
        "schema_version": manifest.get("schema_version"),
        "suite_id": manifest.get("suite_id"),
        "suite_version": manifest.get("suite_version"),
        "dataset": {
            "dataset_id": manifest["dataset"]["dataset_id"],
            "dataset_version": manifest["dataset"]["dataset_version"],
            "dataset_sha256": manifest["dataset"]["dataset_sha256"],
        },
        "corpus": {
            "corpus_id": manifest["corpus"]["corpus_id"],
            "corpus_version": manifest["corpus"]["corpus_version"],
            "corpus_sha256": manifest["corpus"]["corpus_sha256"],
        },
        "condition": {key: value for key, value in condition.items() if key != "compatibility_fingerprint"},
        "evaluation_policy": manifest.get("evaluation_policy"),
    }
    return sha256_json(stable)


def get_condition(manifest: dict[str, Any], condition_id: str) -> dict[str, Any]:
    for condition in manifest.get("conditions", []):
        if condition.get("condition_id") == condition_id:
            return condition
    raise KeyError(f"unknown condition_id: {condition_id}")


def condition_ids(manifest: dict[str, Any]) -> set[str]:
    return {condition["condition_id"] for condition in manifest.get("conditions", [])}


def manifest_artifact_findings(root: Path, manifest: dict[str, Any], manifest_path: Path) -> list[RagFinding]:
    findings: list[RagFinding] = []
    dataset_path = manifest.get("dataset", {}).get("dataset_path")
    if isinstance(dataset_path, str):
        findings.extend(
            validate_ref(
                root,
                {"path": dataset_path, "sha256": manifest.get("dataset", {}).get("dataset_sha256")},
                "RAG_DATASET_REF_INVALID",
                "dataset",
            )
        )
    corpus_path = manifest.get("corpus", {}).get("corpus_snapshot_ref")
    if isinstance(corpus_path, str):
        findings.extend(
            validate_ref(
                root,
                {"path": corpus_path, "sha256": manifest.get("corpus", {}).get("corpus_sha256")},
                "RAG_CORPUS_REF_INVALID",
                "corpus snapshot",
            )
        )
    judge = manifest.get("judge_policy", {})
    calibration_ref = judge.get("calibration_ref")
    if isinstance(calibration_ref, dict):
        findings.extend(validate_ref(root, calibration_ref, "RAG_JUDGE_CALIBRATION_REF_INVALID", "judge calibration"))
    human_sample_ref = judge.get("human_sample_ref")
    if isinstance(human_sample_ref, dict):
        findings.extend(validate_ref(root, human_sample_ref, "RAG_JUDGE_HUMAN_SAMPLE_REF_INVALID", "judge human sample"))
    for index, trace_ref in enumerate(manifest.get("outputs", {}).get("trace_refs", []), 1):
        findings.extend(validate_ref(root, trace_ref, "RAG_TRACE_REF_INVALID", f"trace_refs[{index}]"))
    harness_ref = manifest.get("outputs", {}).get("harness_eval_unit_ref")
    if isinstance(harness_ref, dict):
        findings.extend(validate_ref(root, harness_ref, "RAG_HARNESS_EVAL_UNIT_REF_INVALID", "harness eval unit"))
    return findings


def validate_manifest_semantics(root: Path, manifest: dict[str, Any], manifest_path: Path) -> list[RagFinding]:
    findings: list[RagFinding] = []
    if manifest.get("schema_version") != SCHEMA_VERSION_MANIFEST:
        findings.append(RagFinding("error", "RAG_SCHEMA_VERSION_UNSUPPORTED", "unsupported manifest schema_version", str(manifest_path)))
    seen_conditions: set[str] = set()
    for condition in manifest.get("conditions", []):
        condition_id = condition.get("condition_id", "")
        if condition_id in seen_conditions:
            findings.append(RagFinding("error", "RAG_CONDITION_DUPLICATE", f"duplicate condition_id: {condition_id}", str(manifest_path)))
        seen_conditions.add(condition_id)
        expected = condition.get("compatibility_fingerprint")
        actual = condition_fingerprint(condition)
        if expected != actual:
            findings.append(
                RagFinding(
                    "error",
                    "RAG_CONDITION_FINGERPRINT_MISMATCH",
                    f"condition {condition_id} fingerprint mismatch: expected {expected}, actual {actual}",
                    str(manifest_path),
                )
            )
    baseline_ref = manifest.get("experiment_design", {}).get("baseline_condition_ref")
    if isinstance(baseline_ref, str) and baseline_ref not in seen_conditions:
        findings.append(RagFinding("error", "RAG_BASELINE_CONDITION_UNKNOWN", f"baseline condition not found: {baseline_ref}", str(manifest_path)))
    if manifest.get("evaluation_mode") == "empirical":
        if manifest.get("identity_source") == "unknown":
            findings.append(RagFinding("error", "RAG_EMPIRICAL_IDENTITY_UNKNOWN", "empirical RAG eval cannot use identity_source=unknown", str(manifest_path)))
        head = current_commit(root)
        if head and manifest.get("project_commit") != head:
            findings.append(RagFinding("error", "RAG_EMPIRICAL_HEAD_MISMATCH", "empirical RAG eval project_commit must match current HEAD", str(manifest_path)))
    else:
        head = current_commit(root)
        if head and manifest.get("project_commit") != head:
            findings.append(RagFinding("warning", "RAG_MECHANISM_HEAD_STALE", "mechanism fixture project_commit does not match current HEAD", str(manifest_path)))
    if manifest.get("dirty_state_policy") == "forbid" and current_dirty_state(root):
        findings.append(RagFinding("error", "RAG_DIRTY_STATE_FORBIDDEN", "manifest dirty_state_policy=forbid but worktree is dirty", str(manifest_path)))
    judge = manifest.get("judge_policy", {})
    if judge.get("judge_status") in {"blocking_allowed", "human_confirmed_blocking"}:
        if not isinstance(judge.get("calibration_ref"), dict) or not isinstance(judge.get("human_sample_ref"), dict):
            findings.append(RagFinding("error", "RAG_BLOCKING_JUDGE_UNCALIBRATED", "blocking judge requires calibration_ref and human_sample_ref", str(manifest_path)))
    protected_count = manifest.get("dataset", {}).get("protected_case_count", 0)
    protected = manifest.get("dataset", {}).get("protected_holdout", {})
    if protected_count and protected.get("status") == "none":
        findings.append(RagFinding("error", "RAG_PROTECTED_HOLDOUT_METADATA_INVALID", "protected cases require protected_holdout metadata", str(manifest_path)))
    if protected.get("contamination_status") == "contaminated":
        findings.append(RagFinding("error", "RAG_PROTECTED_HOLDOUT_CONTAMINATED", "contaminated protected holdout cannot satisfy eval evidence", str(manifest_path)))
    return findings


def validate_cases(root: Path, cases: list[dict[str, Any]], cases_path: Path, manifest: dict[str, Any] | None = None) -> list[RagFinding]:
    findings: list[RagFinding] = []
    seen: set[str] = set()
    public_count = 0
    protected_count = 0
    for case in cases:
        findings.extend(validate_schema(root, "rag_eval_case.schema.json", case, cases_path))
        case_id = case.get("case_id")
        if case_id in seen:
            findings.append(RagFinding("error", "RAG_CASE_ID_DUPLICATE", f"duplicate case_id: {case_id}", str(cases_path)))
        seen.add(case_id)
        if case.get("visibility") == "public":
            public_count += 1
        elif case.get("visibility") == "protected":
            protected_count += 1
        if case.get("visibility") == "protected" and case.get("validation_status") == "contaminated":
            findings.append(RagFinding("error", "RAG_PROTECTED_CASE_CONTAMINATED", f"protected case is contaminated: {case_id}", str(cases_path)))
    if manifest is not None:
        dataset = manifest.get("dataset", {})
        if dataset.get("case_count") != len(cases):
            findings.append(RagFinding("error", "RAG_CASE_COUNT_MISMATCH", f"manifest case_count={dataset.get('case_count')} actual={len(cases)}", str(cases_path)))
        if dataset.get("public_case_count") != public_count:
            findings.append(RagFinding("error", "RAG_PUBLIC_CASE_COUNT_MISMATCH", f"manifest public_case_count={dataset.get('public_case_count')} actual={public_count}", str(cases_path)))
        if dataset.get("protected_case_count") != protected_count:
            findings.append(RagFinding("error", "RAG_PROTECTED_CASE_COUNT_MISMATCH", f"manifest protected_case_count={dataset.get('protected_case_count')} actual={protected_count}", str(cases_path)))
        if protected_count and dataset.get("protected_holdout", {}).get("status") == "none":
            findings.append(RagFinding("error", "RAG_PROTECTED_HOLDOUT_METADATA_INVALID", "protected cases require protected holdout boundary metadata", str(cases_path)))
    return findings


def validate_observations(root: Path, observations: list[dict[str, Any]], observations_path: Path, manifest: dict[str, Any], cases: list[dict[str, Any]]) -> list[RagFinding]:
    findings: list[RagFinding] = []
    case_ids = {case["case_id"] for case in cases}
    known_conditions = condition_ids(manifest)
    for observation in observations:
        findings.extend(validate_schema(root, "rag_eval_observation.schema.json", observation, observations_path))
        case_id = observation.get("case_id")
        condition_id = observation.get("condition_id")
        if case_id not in case_ids:
            findings.append(RagFinding("error", "RAG_OBSERVATION_CASE_UNKNOWN", f"observation references unknown case_id: {case_id}", str(observations_path)))
        if condition_id not in known_conditions:
            findings.append(RagFinding("error", "RAG_OBSERVATION_CONDITION_UNKNOWN", f"observation references unknown condition_id: {condition_id}", str(observations_path)))
    return findings


def validate_contract(root: Path, manifest_path: Path, cases_path: Path | None = None, observations_path: Path | None = None, result_path: Path | None = None) -> list[RagFinding]:
    findings: list[RagFinding] = []
    try:
        manifest = load_json(manifest_path)
    except Exception as exc:
        return [RagFinding("error", "RAG_MANIFEST_JSON_INVALID", f"manifest JSON invalid: {exc}", str(manifest_path))]
    findings.extend(validate_schema(root, "rag_eval_manifest.schema.json", manifest, manifest_path))
    findings.extend(validate_manifest_semantics(root, manifest, manifest_path))
    findings.extend(manifest_artifact_findings(root, manifest, manifest_path))
    if cases_path is None:
        resolved_cases = safe_resolve(root, manifest.get("dataset", {}).get("dataset_path", ""))
        cases_path = resolved_cases if resolved_cases is not None else root / "__invalid_cases_path__"
    try:
        cases = load_jsonl(cases_path)
    except Exception as exc:
        findings.append(RagFinding("error", "RAG_CASES_JSONL_INVALID", f"cases JSONL invalid: {exc}", str(cases_path)))
        cases = []
    findings.extend(validate_cases(root, cases, cases_path, manifest))
    if observations_path is not None:
        try:
            observations = load_jsonl(observations_path)
        except Exception as exc:
            findings.append(RagFinding("error", "RAG_OBSERVATIONS_JSONL_INVALID", f"observations JSONL invalid: {exc}", str(observations_path)))
            observations = []
        findings.extend(validate_observations(root, observations, observations_path, manifest, cases))
    if result_path is not None:
        try:
            result = load_json(result_path)
        except Exception as exc:
            findings.append(RagFinding("error", "RAG_RESULT_JSON_INVALID", f"result JSON invalid: {exc}", str(result_path)))
        else:
            findings.extend(validate_schema(root, "rag_eval_result.schema.json", result, result_path))
            findings.extend(validate_result_identity(root, result, manifest, result_path))
    return findings


def validate_result_identity(root: Path, result: dict[str, Any], manifest: dict[str, Any], result_path: Path) -> list[RagFinding]:
    findings: list[RagFinding] = []
    for key, label in (("manifest_ref", "manifest"), ("cases_ref", "cases"), ("observations_ref", "observations")):
        ref = result.get(key)
        if isinstance(ref, dict):
            findings.extend(validate_ref(root, ref, f"RAG_RESULT_{key.upper()}_INVALID", label))
    dataset = manifest.get("dataset", {})
    if result.get("dataset_identity", {}).get("dataset_sha256") != dataset.get("dataset_sha256"):
        findings.append(RagFinding("error", "RAG_RESULT_DATASET_IDENTITY_MISMATCH", "result dataset identity does not match manifest", str(result_path)))
    corpus = manifest.get("corpus", {})
    if result.get("corpus_identity", {}).get("corpus_sha256") != corpus.get("corpus_sha256"):
        findings.append(RagFinding("error", "RAG_RESULT_CORPUS_IDENTITY_MISMATCH", "result corpus identity does not match manifest", str(result_path)))
    condition_id = result.get("condition_id")
    try:
        expected_fingerprint = config_fingerprint(manifest, str(condition_id))
    except Exception:
        findings.append(RagFinding("error", "RAG_RESULT_CONDITION_UNKNOWN", f"result condition unknown: {condition_id}", str(result_path)))
    else:
        if result.get("config_fingerprint") != expected_fingerprint:
            findings.append(RagFinding("error", "RAG_RESULT_CONFIG_FINGERPRINT_MISMATCH", "result config_fingerprint does not match manifest inputs", str(result_path)))
    return findings


def evidence_key(item: dict[str, Any]) -> tuple[str, str | None, str | None]:
    return (str(item.get("doc_id")), item.get("chunk_id"), item.get("span_id"))


def doc_key(item: dict[str, Any]) -> str:
    return str(item.get("doc_id"))


def relevant_sets(case: dict[str, Any]) -> tuple[set[tuple[str, str | None, str | None]], set[str]]:
    refs = [*case.get("expected_evidence", []), *case.get("acceptable_evidence", [])]
    return {evidence_key(ref) for ref in refs}, {doc_key(ref) for ref in refs}


def forbidden_doc_set(case: dict[str, Any]) -> set[str]:
    return {doc_key(ref) for ref in case.get("forbidden_evidence", [])}


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * pct
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return sorted_values[int(rank)]
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (rank - lower)


def ndcg_binary(relevance: list[int], ideal_relevant_count: int) -> float:
    def dcg(vals: list[int]) -> float:
        return sum(value / math.log2(index + 2) for index, value in enumerate(vals))

    ideal = [1] * min(ideal_relevant_count, len(relevance)) + [0] * max(0, len(relevance) - ideal_relevant_count)
    ideal_score = dcg(ideal)
    return 0.0 if ideal_score == 0 else dcg(relevance) / ideal_score


def metric_mean(values: list[float]) -> float | None:
    return None if not values else sum(values) / len(values)


def classify_stop_ship(manifest: dict[str, Any], cases: list[dict[str, Any]], observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stop_ship: list[dict[str, Any]] = []
    by_case = {case["case_id"]: case for case in cases}
    risk = manifest.get("risk_level", "medium")
    for observation in observations:
        case = by_case.get(observation.get("case_id"))
        if case is None:
            continue
        case_id = case["case_id"]
        forbidden = forbidden_doc_set(case)
        retrieved_docs = [doc_key(item) for item in observation.get("retrieved_items", [])]
        context_docs = [doc_key(item) for item in observation.get("assembled_context", {}).get("items", [])]
        cited_docs = [doc_key(item) for item in observation.get("citations", [])]
        if "permission" in case.get("slices", []) and forbidden.intersection([*retrieved_docs, *context_docs, *cited_docs]):
            stop_ship.append({"rule_id": "ACL_LEAK", "severity": "P0", "message": "unauthorized restricted evidence was retrieved, assembled, or cited", "case_id": case_id})
        if any(item.get("acl_result") == "denied" for item in observation.get("retrieved_items", [])):
            stop_ship.append({"rule_id": "UNAUTHORIZED_DOCUMENT_RETRIEVED", "severity": "P0", "message": "retrieved item has acl_result=denied", "case_id": case_id})
        if case.get("freshness_expectation", {}).get("requires_current"):
            first = sorted(observation.get("retrieved_items", []), key=lambda item: item.get("rank", 999999))[:1]
            stale_ids = set(case.get("freshness_expectation", {}).get("stale_doc_ids", []))
            if first and first[0].get("doc_id") in stale_ids:
                stop_ship.append({"rule_id": "STALE_REQUIRED_DOC_WINS", "severity": "P0", "message": "stale document ranked first where freshness is required", "case_id": case_id})
        if case.get("no_answer_expected") and not observation.get("insufficient_evidence"):
            stop_ship.append({"rule_id": "NO_ANSWER_PATH_MISSING", "severity": "P0", "message": "no-answer case did not return insufficient_evidence", "case_id": case_id})
        for citation in observation.get("citations", []):
            if citation.get("supports_claim") is False:
                severity = "P0" if risk in {"high", "critical"} else "P1"
                stop_ship.append({"rule_id": "CITATION_UNSUPPORTED", "severity": severity, "message": "citation does not support claim", "case_id": case_id})
        relevant_keys, relevant_docs = relevant_sets(case)
        if observation.get("answer_correct") is True and not case.get("no_answer_expected"):
            retrieved_keys = {evidence_key(item) for item in observation.get("retrieved_items", [])}
            retrieved_doc_ids = {doc_key(item) for item in observation.get("retrieved_items", [])}
            if relevant_keys and not (retrieved_keys & relevant_keys or retrieved_doc_ids & relevant_docs):
                stop_ship.append({"rule_id": "E2E_HIDES_RETRIEVAL_FAILURE", "severity": "P1", "message": "answer marked correct while expected evidence was not retrieved", "case_id": case_id})
        perturbation = observation.get("perturbation")
        if perturbation and perturbation.get("human_relevance_label") is None and perturbation.get("gold_attribution_label") is None:
            stop_ship.append({"rule_id": "GRAPH_ATTRIBUTION_SELF_REFERENTIAL", "severity": "P1", "message": "graph attribution uses answer shift without independent label", "case_id": case_id})
    protected = manifest.get("dataset", {}).get("protected_holdout", {})
    if protected.get("contamination_status") == "contaminated":
        stop_ship.append({"rule_id": "PROTECTED_HOLDOUT_CONTAMINATED", "severity": "P0", "message": "protected holdout is contaminated", "case_id": None})
    return stop_ship


def score_observations(root: Path, manifest_path: Path, cases_path: Path, observations_path: Path, condition_id: str) -> tuple[dict[str, Any], list[RagFinding]]:
    manifest = load_json(manifest_path)
    cases = load_jsonl(cases_path)
    observations_all = load_jsonl(observations_path)
    observations = [item for item in observations_all if item.get("condition_id") == condition_id]
    findings = validate_contract(root, manifest_path, cases_path, observations_path)
    if not observations:
        findings.append(RagFinding("error", "RAG_SCORE_NO_OBSERVATIONS", f"no observations for condition_id={condition_id}", str(observations_path)))
    by_case = {case["case_id"]: case for case in cases}
    answerable_cases = [case for case in cases if not case.get("no_answer_expected")]
    k = get_condition(manifest, condition_id)["top_k"]
    retrieval_values: dict[str, list[float]] = defaultdict(list)
    no_answer_values: list[float] = []
    stale_values: list[float] = []
    citation_trace_values: list[float] = []
    duplicate_context_rates: list[float] = []
    forbidden_hits: list[float] = []
    acl_hits: list[float] = []
    route_domain_values: list[float] = []
    route_collection_values: list[float] = []
    route_coverage_values: list[float] = []
    wrong_route_values: list[float] = []
    fallback_values: list[float] = []
    cross_domain_values: list[float] = []
    no_route_values: list[float] = []
    retrieval_calls: list[float] = []
    retry_counts: list[float] = []
    returned = 0
    consumed = 0
    timeout_count = 0
    termination_counter: Counter[str] = Counter()
    failure_counter: Counter[str] = Counter()
    retrieval_latencies: list[float] = []
    e2e_latencies: list[float] = []
    costs: list[float] = []
    successes = 0
    attempts = 0
    answer_correct_by_noise: dict[str, list[float]] = defaultdict(list)
    perturb_answer_change: list[float] = []
    perturb_irrelevant_invariance: list[float] = []
    perturb_label_pairs: list[tuple[float, float]] = []
    per_trial: list[dict[str, Any]] = []
    by_slice_accum: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for observation in observations:
        case = by_case.get(observation.get("case_id"))
        if case is None:
            continue
        attempts += 1
        if observation.get("answer_correct") is True:
            successes += 1
        top_items = sorted(observation.get("retrieved_items", []), key=lambda item: item.get("rank", 999999))[:k]
        relevant_keys, relevant_docs = relevant_sets(case)
        forbidden_docs = forbidden_doc_set(case)
        if not case.get("no_answer_expected"):
            hits = [1 if evidence_key(item) in relevant_keys or doc_key(item) in relevant_docs else 0 for item in top_items]
            hit = 1.0 if any(hits) else 0.0
            expected_count = max(1, len(relevant_keys) or len(relevant_docs))
            recall = min(sum(hits), expected_count) / expected_count
            precision = sum(hits) / len(top_items) if top_items else 0.0
            mrr = 0.0
            for index, value in enumerate(hits, 1):
                if value:
                    mrr = 1.0 / index
                    break
            ndcg = ndcg_binary(hits, expected_count)
            for metric_id, value in (
                ("retrieval.hit_at_3", hit),
                ("retrieval.recall_at_3", recall),
                ("retrieval.precision_at_3", precision),
                ("retrieval.mrr", mrr),
                ("retrieval.ndcg_at_3", ndcg),
                ("retrieval.evidence_span_coverage", recall),
            ):
                retrieval_values[metric_id].append(value)
                for slice_name in case.get("slices", []):
                    by_slice_accum[slice_name][metric_id].append(value)
        no_answer_ok = 1.0 if (case.get("no_answer_expected") == bool(observation.get("insufficient_evidence"))) else 0.0
        no_answer_values.append(no_answer_ok)
        for slice_name in case.get("slices", []):
            by_slice_accum[slice_name]["generation.no_answer_accuracy"].append(no_answer_ok)
        context_keys = [evidence_key(item) for item in observation.get("assembled_context", {}).get("items", [])]
        duplicate_rate = 0.0 if not context_keys else (len(context_keys) - len(set(context_keys))) / len(context_keys)
        duplicate_context_rates.append(duplicate_rate)
        cited_context = {evidence_key(item) for item in observation.get("assembled_context", {}).get("items", [])}
        citation_ok = all(citation.get("supports_claim") is True and evidence_key(citation) in cited_context for citation in observation.get("citations", []))
        citation_trace_values.append(1.0 if citation_ok else 0.0)
        observed_docs = [doc_key(item) for item in observation.get("retrieved_items", [])]
        observed_docs.extend(doc_key(item) for item in observation.get("assembled_context", {}).get("items", []))
        observed_docs.extend(doc_key(item) for item in observation.get("citations", []))
        forbidden = 1.0 if forbidden_docs.intersection(observed_docs) else 0.0
        forbidden_hits.append(forbidden)
        acl_leak = 1.0 if any(item.get("acl_result") == "denied" for item in observation.get("retrieved_items", [])) else 0.0
        if "permission" in case.get("slices", []) and forbidden:
            acl_leak = 1.0
        acl_hits.append(acl_leak)
        for slice_name in case.get("slices", []):
            by_slice_accum[slice_name]["retrieval.acl_leak_rate"].append(acl_leak)
        if case.get("freshness_expectation", {}).get("requires_current"):
            stale_ids = set(case.get("freshness_expectation", {}).get("stale_doc_ids", []))
            first = top_items[:1]
            stale_values.append(1.0 if first and first[0].get("doc_id") not in stale_ids else 0.0)
        expected_route = case.get("expected_route") or {}
        route = observation.get("route_decision", {})
        if expected_route.get("domain") is not None:
            domain_ok = 1.0 if route.get("domain") == expected_route.get("domain") else 0.0
            collection_ok = 1.0 if route.get("collection") == expected_route.get("collection") else 0.0
            covered = 1.0 if route.get("domain") is not None and route.get("collection") is not None else 0.0
            wrong = 1.0 if covered and (not domain_ok or not collection_ok) else 0.0
            cross = 1.0 if any(item.get("domain") not in {None, expected_route.get("domain")} for item in observation.get("retrieved_items", [])) else 0.0
            for collection, value in (
                (route_domain_values, domain_ok),
                (route_collection_values, collection_ok),
                (route_coverage_values, covered),
                (wrong_route_values, wrong),
                (cross_domain_values, cross),
            ):
                collection.append(value)
            fallback_values.append(1.0 if route.get("fallback_used") else 0.0)
            no_route_values.append(1.0 if route.get("no_route") else 0.0)
            for slice_name in case.get("slices", []):
                by_slice_accum[slice_name]["routing.domain_match_accuracy"].append(domain_ok)
                by_slice_accum[slice_name]["routing.collection_match_accuracy"].append(collection_ok)
        harness = observation.get("harness_events", {})
        retrieval_calls.append(float(harness.get("retrieval_calls", 0)))
        retry_counts.append(float(harness.get("retries", 0)))
        returned += int(harness.get("returned_result_count", 0))
        consumed += int(harness.get("consumed_result_count", 0))
        termination = str(harness.get("termination_reason"))
        termination_counter[termination] += 1
        if termination == "timeout":
            timeout_count += 1
        failure_stage = observation.get("failure_stage")
        if failure_stage:
            failure_counter[str(failure_stage)] += 1
        latencies = observation.get("latency_ms", {})
        if isinstance(latencies.get("retrieval"), (int, float)):
            retrieval_latencies.append(float(latencies["retrieval"]))
        if isinstance(latencies.get("e2e"), (int, float)):
            e2e_latencies.append(float(latencies["e2e"]))
        cost = observation.get("cost", {}).get("total_usd")
        if isinstance(cost, (int, float)):
            costs.append(float(cost))
        noise = case.get("noise_scenario")
        if noise:
            answer_correct_by_noise[str(noise)].append(1.0 if observation.get("answer_correct") else 0.0)
        perturb = observation.get("perturbation")
        if perturb:
            change = float(perturb.get("answer_change_score", 0.0))
            perturb_answer_change.append(change)
            if perturb.get("expected_irrelevant"):
                perturb_irrelevant_invariance.append(1.0 - min(1.0, change))
            label = perturb.get("human_relevance_label")
            if isinstance(label, (int, float)):
                perturb_label_pairs.append((change, float(label)))
        per_trial.append(
            {
                "case_id": case["case_id"],
                "trial_id": observation.get("trial_id"),
                "answer_correct": observation.get("answer_correct"),
                "failure_stage": observation.get("failure_stage"),
            }
        )

    metrics: dict[str, Any] = {metric_id: metric_mean(values) for metric_id, values in retrieval_values.items()}
    metrics.update(
        {
            "generation.no_answer_accuracy": metric_mean(no_answer_values),
            "generation.citation_traceability": metric_mean(citation_trace_values),
            "retrieval.duplicate_context_rate": metric_mean(duplicate_context_rates),
            "retrieval.forbidden_evidence_rate": metric_mean(forbidden_hits),
            "retrieval.acl_leak_rate": metric_mean(acl_hits),
            "retrieval.stale_doc_rejection": metric_mean(stale_values) if stale_values else None,
            "routing.domain_match_accuracy": metric_mean(route_domain_values),
            "routing.collection_match_accuracy": metric_mean(route_collection_values),
            "routing.route_coverage": metric_mean(route_coverage_values),
            "routing.wrong_route_rate": metric_mean(wrong_route_values),
            "routing.fallback_rate": metric_mean(fallback_values),
            "routing.cross_domain_leakage_rate": metric_mean(cross_domain_values),
            "routing.no_route_rate": metric_mean(no_route_values),
            "harness.avg_retrieval_call_count": metric_mean(retrieval_calls),
            "harness.returned_results_consumed_ratio": (consumed / returned) if returned else 1.0,
            "harness.avg_retry_count": metric_mean(retry_counts),
            "harness.timeout_rate": (timeout_count / attempts) if attempts else None,
            "latency.retrieval_p50_ms": percentile(retrieval_latencies, 0.5),
            "latency.retrieval_p95_ms": percentile(retrieval_latencies, 0.95),
            "latency.e2e_p50_ms": percentile(e2e_latencies, 0.5),
            "latency.e2e_p95_ms": percentile(e2e_latencies, 0.95),
            "cost.cost_per_attempt_usd": metric_mean(costs),
            "cost.cost_per_success_usd": (sum(costs) / successes) if successes else None,
            "robustness.answer_accuracy_by_noise": {key: metric_mean(values) for key, values in sorted(answer_correct_by_noise.items())},
            "robustness.high_noise_degradation": (
                (metric_mean(answer_correct_by_noise.get("clean", [])) or 0.0)
                - (metric_mean(answer_correct_by_noise.get("high_noise", [])) or 0.0)
                if answer_correct_by_noise.get("high_noise")
                else None
            ),
            "perturbation.answer_change_sensitivity": metric_mean(perturb_answer_change),
            "perturbation.irrelevant_evidence_invariance": metric_mean(perturb_irrelevant_invariance),
            "perturbation.agreement_with_human_labels": perturbation_label_agreement(perturb_label_pairs),
            "perturbation.coverage": len(perturb_answer_change),
        }
    )
    by_slice: dict[str, dict[str, Any]] = {
        slice_name: {metric_id: metric_mean(values) for metric_id, values in metric_values.items()}
        for slice_name, metric_values in sorted(by_slice_accum.items())
    }
    stop_ship = classify_stop_ship(manifest, cases, observations)
    validation_errors = [finding for finding in findings if finding.severity == "error"]
    status = "invalid" if validation_errors else "fail" if stop_ship else "pass"
    condition = get_condition(manifest, condition_id)
    result = {
        "schema_version": SCHEMA_VERSION_RESULT,
        "result_id": f"{manifest['suite_id']}:{condition_id}:{Path(observations_path).stem}",
        "status": status,
        "generated_at": utc_now(),
        "project_commit": current_commit(root) or manifest["project_commit"],
        "dirty_state": {"policy": manifest.get("dirty_state_policy", "record_only"), "entries": current_dirty_state(root)},
        "config_fingerprint": config_fingerprint(manifest, condition_id),
        "manifest_ref": artifact_ref(manifest_path, root, kind="rag_eval_manifest"),
        "cases_ref": artifact_ref(cases_path, root, kind="rag_eval_cases"),
        "observations_ref": artifact_ref(observations_path, root, kind="rag_eval_observations"),
        "dataset_identity": {
            "dataset_id": manifest["dataset"]["dataset_id"],
            "dataset_version": manifest["dataset"]["dataset_version"],
            "dataset_sha256": manifest["dataset"]["dataset_sha256"],
            "dataset_source": manifest["dataset"]["dataset_source"],
        },
        "corpus_identity": {
            "corpus_id": manifest["corpus"]["corpus_id"],
            "corpus_version": manifest["corpus"]["corpus_version"],
            "corpus_sha256": manifest["corpus"]["corpus_sha256"],
        },
        "condition_id": condition_id,
        "condition_identity": condition,
        "scorer_identity": {"tool": "tools/rag_eval_score.py", "version": SCORER_VERSION},
        "judge_identity": {
            "judge_status": manifest["judge_policy"]["judge_status"],
            "judge_model": manifest["judge_policy"].get("judge_model"),
            "calibration_ref": manifest["judge_policy"].get("calibration_ref"),
        },
        "metrics": metrics,
        "by_slice": by_slice,
        "sample_counts": {
            "cases": len(cases),
            "answerable_cases": len(answerable_cases),
            "observations": len(observations),
            "trials": len({item.get("trial_id") for item in observations}),
            "invalid_findings": len(validation_errors),
        },
        "per_trial_metrics": per_trial,
        "invalid_cases": [{"case_id": "", "reason": finding.message} for finding in validation_errors],
        "failure_taxonomy": dict(failure_counter),
        "stop_ship_findings": stop_ship,
        "latency_cost_rollups": {
            "termination_distribution": dict(termination_counter),
            "retrieval_latency_ms": {"p50": percentile(retrieval_latencies, 0.5), "p95": percentile(retrieval_latencies, 0.95)},
            "e2e_latency_ms": {"p50": percentile(e2e_latencies, 0.5), "p95": percentile(e2e_latencies, 0.95)},
            "total_cost_usd": sum(costs) if costs else 0.0,
        },
        "external_scorer_outputs": [],
    }
    result_findings = validate_schema(root, "rag_eval_result.schema.json", result, Path("<generated-result>"))
    findings.extend(result_findings)
    if result_findings:
        result["status"] = "invalid"
        result["invalid_cases"].extend({"case_id": "", "reason": finding.message} for finding in result_findings)
    return result, findings


def perturbation_label_agreement(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    correct = 0
    for score, label in pairs:
        correct += int((score >= 0.5) == (label >= 0.5))
    return correct / len(pairs)


def flatten_numeric(prefix: str, value: Any, output: dict[str, float]) -> None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        output[prefix] = float(value)
    elif isinstance(value, dict):
        for key, nested in value.items():
            flatten_numeric(f"{prefix}.{key}" if prefix else str(key), nested, output)


def numeric_metrics(result: dict[str, Any]) -> dict[str, float]:
    output: dict[str, float] = {}
    for key, value in result.get("metrics", {}).items():
        flatten_numeric(key, value, output)
    return output


def compare_results(root: Path, manifest_path: Path, baseline_path: Path, candidate_path: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    baseline = load_json(baseline_path)
    candidate = load_json(candidate_path)
    compatibility_errors: list[str] = []
    for field in ("dataset_identity", "corpus_identity"):
        if baseline.get(field) != candidate.get(field):
            compatibility_errors.append(f"{field} differs between baseline and candidate")
    if baseline.get("status") == "invalid" or candidate.get("status") == "invalid":
        compatibility_errors.append("invalid result cannot satisfy baseline comparison")
    policies = {metric["metric_id"]: metric for metric in manifest.get("evaluation_policy", {}).get("metrics", [])}
    abs_thresholds = manifest.get("evaluation_policy", {}).get("absolute_regression_thresholds", {"p1": 0.05, "p0": 0.15})
    rel_thresholds = manifest.get("evaluation_policy", {}).get("relative_regression_thresholds", {"p1": 0.05, "p0": 0.15})
    baseline_metrics = numeric_metrics(baseline)
    candidate_metrics = numeric_metrics(candidate)
    metric_deltas: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for metric_id, policy in policies.items():
        base = baseline_metrics.get(metric_id)
        cand = candidate_metrics.get(metric_id)
        delta = None if base is None or cand is None else cand - base
        severity = "invalid" if base is None or cand is None else "none"
        message = ""
        relative_delta = None
        if base is not None and cand is not None:
            regression = base - cand if policy["direction"] == "higher_is_better" else cand - base
            if abs(base) > 1e-12:
                relative_delta = regression / abs(base)
            abs_regression = regression
            if not policy.get("release_significant", False):
                severity = "none"
            elif abs_regression > abs_thresholds.get("p0", 0.15) or (relative_delta is not None and relative_delta > rel_thresholds.get("p0", 0.15)):
                severity = "P0"
            elif abs_regression > abs_thresholds.get("p1", 0.05) or (relative_delta is not None and relative_delta > rel_thresholds.get("p1", 0.05)):
                severity = "P1"
            if severity in {"P0", "P1"}:
                message = f"{metric_id} regressed under {policy['direction']}"
                findings.append({"rule_id": "RAG_METRIC_REGRESSION", "severity": severity, "message": message, "metric_id": metric_id, "slice": None})
        metric_deltas.append(
            {
                "metric_id": metric_id,
                "direction": policy["direction"],
                "baseline": base,
                "candidate": cand,
                "absolute_delta": delta,
                "relative_delta": relative_delta,
                "severity": severity,
                "message": message,
            }
        )
    per_slice_deltas: list[dict[str, Any]] = []
    baseline_slices = baseline.get("by_slice", {})
    candidate_slices = candidate.get("by_slice", {})
    for slice_name in sorted(set(baseline_slices) | set(candidate_slices)):
        base_flat: dict[str, float] = {}
        cand_flat: dict[str, float] = {}
        for key, value in baseline_slices.get(slice_name, {}).items():
            flatten_numeric(key, value, base_flat)
        for key, value in candidate_slices.get(slice_name, {}).items():
            flatten_numeric(key, value, cand_flat)
        for metric_id, policy in policies.items():
            if metric_id not in base_flat and metric_id not in cand_flat:
                continue
            base = base_flat.get(metric_id)
            cand = cand_flat.get(metric_id)
            delta = None if base is None or cand is None else cand - base
            severity = "invalid" if base is None or cand is None else "none"
            relative_delta = None
            message = ""
            if base is not None and cand is not None:
                regression = base - cand if policy["direction"] == "higher_is_better" else cand - base
                if abs(base) > 1e-12:
                    relative_delta = regression / abs(base)
                if not policy.get("release_significant", False):
                    severity = "none"
                elif regression > abs_thresholds.get("p0", 0.15) or (relative_delta is not None and relative_delta > rel_thresholds.get("p0", 0.15)):
                    severity = "P0"
                elif regression > abs_thresholds.get("p1", 0.05) or (relative_delta is not None and relative_delta > rel_thresholds.get("p1", 0.05)):
                    severity = "P1"
                if severity in {"P0", "P1"}:
                    message = f"{metric_id} regressed on slice {slice_name}"
                    findings.append({"rule_id": "RAG_SLICE_REGRESSION", "severity": severity, "message": message, "metric_id": metric_id, "slice": slice_name})
            per_slice_deltas.append(
                {
                    "slice": slice_name,
                    "metric_id": metric_id,
                    "baseline": base,
                    "candidate": cand,
                    "absolute_delta": delta,
                    "relative_delta": relative_delta,
                    "severity": severity,
                    "message": message,
                }
            )
    stop_ship: list[dict[str, Any]] = []
    for source_name, result in (("baseline", baseline), ("candidate", candidate)):
        for finding in result.get("stop_ship_findings", []):
            stop_ship.append(
                {
                    "rule_id": f"{source_name}:{finding.get('rule_id')}",
                    "severity": finding.get("severity", "P0"),
                    "message": finding.get("message", ""),
                    "metric_id": None,
                    "slice": None,
                }
            )
    compatible = not compatibility_errors
    status = "invalid" if not compatible else "fail" if findings or stop_ship else "pass"
    comparison = {
        "schema_version": SCHEMA_VERSION_COMPARISON,
        "comparison_id": f"{baseline.get('condition_id')}..{candidate.get('condition_id')}",
        "status": status,
        "generated_at": utc_now(),
        "manifest_ref": artifact_ref(manifest_path, root, kind="rag_eval_manifest"),
        "baseline_result_ref": artifact_ref(baseline_path, root, kind="rag_eval_result"),
        "candidate_result_ref": artifact_ref(candidate_path, root, kind="rag_eval_result"),
        "compatible": compatible,
        "compatibility_errors": compatibility_errors,
        "changed_factors": manifest.get("experiment_design", {}).get("changed_factors", []),
        "metric_deltas": metric_deltas,
        "per_slice_deltas": per_slice_deltas,
        "regression_findings": findings,
        "stop_ship_findings": stop_ship,
        "markdown_report_ref": {"path": "reports/rag_eval/comparison.md", "sha256": "0" * 64, "kind": "markdown_report"},
    }
    return comparison


def render_score_report(result: dict[str, Any]) -> str:
    lines = [
        "# RAG Eval Result",
        "",
        f"Result ID: `{result['result_id']}`",
        f"Status: `{result['status']}`",
        f"Condition: `{result['condition_id']}`",
        f"Config fingerprint: `{result['config_fingerprint']}`",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
    ]
    for key, value in sorted(result.get("metrics", {}).items()):
        if isinstance(value, dict):
            value_text = json.dumps(value, sort_keys=True)
        else:
            value_text = str(value)
        lines.append(f"| `{key}` | `{value_text}` |")
    lines.extend(["", "## Stop-Ship Findings", ""])
    if result.get("stop_ship_findings"):
        for finding in result["stop_ship_findings"]:
            lines.append(f"- `{finding['severity']}` `{finding['rule_id']}` {finding['message']} ({finding.get('case_id')})")
    else:
        lines.append("none")
    lines.append("")
    return "\n".join(lines)


def render_comparison_report(comparison: dict[str, Any]) -> str:
    lines = [
        "# RAG Eval Comparison",
        "",
        f"Status: `{comparison['status']}`",
        f"Compatible: `{comparison['compatible']}`",
        "",
        "## Metric Deltas",
        "",
        "| Metric | Baseline | Candidate | Delta | Severity |",
        "|--------|----------|-----------|-------|----------|",
    ]
    for delta in comparison.get("metric_deltas", []):
        lines.append(
            f"| `{delta['metric_id']}` | `{delta['baseline']}` | `{delta['candidate']}` | `{delta['absolute_delta']}` | `{delta['severity']}` |"
        )
    lines.extend(["", "## Findings", ""])
    all_findings = [*comparison.get("regression_findings", []), *comparison.get("stop_ship_findings", [])]
    if all_findings:
        for finding in all_findings:
            lines.append(f"- `{finding['severity']}` `{finding['rule_id']}` {finding['message']}")
    else:
        lines.append("none")
    if comparison.get("compatibility_errors"):
        lines.extend(["", "## Compatibility Errors", ""])
        for error in comparison["compatibility_errors"]:
            lines.append(f"- {error}")
    lines.append("")
    return "\n".join(lines)
