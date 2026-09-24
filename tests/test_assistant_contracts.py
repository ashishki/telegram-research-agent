"""PA-01 contract and synthetic-corpus acceptance checks; all inputs are offline."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
CORPUS_PATH = ROOT / "tests" / "fixtures" / "assistant" / "pa01_acceptance_corpus.v1.json"
CONTRACT_SCHEMAS = {
    "capability_grant": "assistant_capability_grant.v1.schema.json",
    "tool_result": "assistant_tool_result.v1.schema.json",
    "evidence_item": "assistant_evidence_item.v1.schema.json",
    "brief_document": "assistant_brief_document.v1.schema.json",
    "action_proposal": "assistant_action_proposal.v1.schema.json",
    "action_receipt": "assistant_action_receipt.v1.schema.json",
}
ALL_FUTURE_SLICES = {f"PA-{number:02d}" for number in range(2, 19)}
ALL_SOURCE_CLASSES = {
    "telegram_archive",
    "public_web",
    "mail",
    "calendar",
    "canvas",
    "github",
    "document",
    "academic_public",
    "user_provided",
}
FORBIDDEN_KEY = re.compile(r"(?:token|secret|password|authorization|cookie)", re.IGNORECASE)
FORBIDDEN_VALUE = re.compile(r"(?:sk-[a-z0-9]{8,}|bearer\\s+|-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----)", re.IGNORECASE)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(contract_name: str) -> Draft202012Validator:
    return Draft202012Validator(
        _load_json(SCHEMA_DIR / CONTRACT_SCHEMAS[contract_name]),
        format_checker=FormatChecker(),
    )


def _errors(contract_name: str, value: object) -> list[str]:
    return [error.message for error in _validator(contract_name).iter_errors(value)]


def _walk(value: object, path: str = "$"):
    if isinstance(value, dict):
        for key, nested in value.items():
            key_path = f"{path}.{key}"
            yield key_path, key, nested
            yield from _walk(nested, key_path)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _walk(nested, f"{path}[{index}]")


def test_pa01_contract_examples_validate_and_are_explicitly_versioned():
    corpus = _load_json(CORPUS_PATH)

    assert corpus["schema_version"] == "assistant.acceptance_corpus.v1"
    assert set(corpus["contract_examples"]) == set(CONTRACT_SCHEMAS)
    for contract_name, schema_name in CONTRACT_SCHEMAS.items():
        schema = _load_json(SCHEMA_DIR / schema_name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False
        assert not _errors(contract_name, corpus["contract_examples"][contract_name])


def test_pa01_contracts_reject_malformed_authority_and_outcome_states():
    corpus = _load_json(CORPUS_PATH)["contract_examples"]

    revoked_grant = copy.deepcopy(corpus["capability_grant"])
    revoked_grant["provider_policy"]["egress"] = "allow"
    revoked_grant["provider_policy"]["permitted_provider_refs"] = []
    assert _errors("capability_grant", revoked_grant)

    revoked_without_time = copy.deepcopy(corpus["capability_grant"])
    revoked_without_time["status"] = "revoked"
    assert _errors("capability_grant", revoked_without_time)

    denied_result = copy.deepcopy(corpus["tool_result"])
    denied_result.update({"status": "denied", "data": corpus["tool_result"]["data"], "evidence_refs": []})
    assert _errors("tool_result", denied_result)

    malformed_evidence = copy.deepcopy(corpus["evidence_item"])
    malformed_evidence["source_kind"] = "untrusted_shell"
    assert _errors("evidence_item", malformed_evidence)

    uncited_brief = copy.deepcopy(corpus["brief_document"])
    uncited_brief["sections"][0]["items"][0]["evidence_refs"] = []
    assert _errors("brief_document", uncited_brief)

    reusable_confirmation = copy.deepcopy(corpus["action_proposal"])
    reusable_confirmation["confirmation"]["single_use"] = False
    assert _errors("action_proposal", reusable_confirmation)

    unknown_as_failure = copy.deepcopy(corpus["action_receipt"])
    unknown_as_failure.update({"execution_state": "unknown", "completed_at": None, "reconciliation_required": False})
    assert _errors("action_receipt", unknown_as_failure)


def test_pa01_contract_chain_preserves_result_version_and_idempotency():
    examples = _load_json(CORPUS_PATH)["contract_examples"]
    tool_result = examples["tool_result"]
    evidence = examples["evidence_item"]
    brief = examples["brief_document"]
    proposal = examples["action_proposal"]
    receipt = examples["action_receipt"]

    assert tool_result["data"]["result_ref"] == tool_result["result_id"]
    assert evidence["evidence_id"] in tool_result["evidence_refs"]
    assert evidence["evidence_id"] in brief["evidence_refs"]
    assert all(
        evidence_ref in brief["evidence_refs"]
        for section in brief["sections"]
        for item in section["items"]
        for evidence_ref in item["evidence_refs"]
    )
    assert proposal["source_result"]["result_ref"] == tool_result["result_id"]
    assert receipt["proposal_ref"] == proposal["proposal_id"]
    assert receipt["proposal_version"] == proposal["proposal_version"]
    assert receipt["source_result"] == {key: proposal["source_result"][key] for key in ("result_ref", "version")}
    assert receipt["idempotency_key"] == proposal["idempotency_key"]


def test_pa01_corpus_covers_every_future_slice_source_class_and_risk_mode():
    corpus = _load_json(CORPUS_PATH)
    scenarios = corpus["scenarios"]
    represented_slices = {slice_id for scenario in scenarios for slice_id in scenario["slices"]}
    represented_sources = {source for scenario in scenarios for source in scenario["source_classes"]}
    represented_kinds = {scenario["kind"] for scenario in scenarios}

    assert represented_slices == ALL_FUTURE_SLICES
    assert ALL_SOURCE_CLASSES <= represented_sources
    assert {"positive", "negative", "adversarial", "failure_recovery", "human_gate"} <= represented_kinds
    final_gate = next(scenario for scenario in scenarios if scenario["scenario_id"] == "pa18_integrated_owner_acceptance")
    assert "fixture_not_release_evidence" in final_gate["expected"]


def test_pa01_public_corpus_contains_no_credential_shaped_keys_or_values():
    corpus = _load_json(CORPUS_PATH)
    assert corpus["privacy"] == {
        "contains_private_content": False,
        "contains_credentials": False,
        "contains_live_account_identifiers": False,
        "synthetic_only": True,
    }
    for path, key, value in _walk(corpus):
        assert not FORBIDDEN_KEY.search(key), path
        if isinstance(value, str):
            assert not FORBIDDEN_VALUE.search(value), path
