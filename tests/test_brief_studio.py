import importlib.util
from pathlib import Path

import pytest


def _module(name="brief_studio_test"):
    path = Path(__file__).parents[1] / "tools" / "brief_studio.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_parse_model_json_tolerates_fences_and_literal_newlines():
    module = _module()
    assert module._parse_model_json('{"a": 1}') == {"a": 1}
    assert module._parse_model_json('```json\n{"a": 1}\n```') == {"a": 1}
    # A literal newline inside a string is invalid JSON but common from models.
    assert module._parse_model_json('{"a": "line1\nline2"}') == {"a": "line1 line2"}
    assert module._parse_model_json('here you go: {"a": 2} thanks') == {"a": 2}
    with pytest.raises(ValueError):
        module._parse_model_json("not json at all")


def test_brief_studio_parser_defaults_are_safe():
    module = _module("brief_studio_parser")
    args = module.build_parser().parse_args([])
    assert args.allow_provider_egress is False
    assert args.editorial_retries >= 1
    assert args.model
