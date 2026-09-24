import importlib.util
from pathlib import Path


def _module(name="profile_ranked_brief_test"):
    path = Path(__file__).parents[1] / "tools" / "profile_ranked_brief.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_match_terms_is_word_bounded():
    module = _module()
    hits = module._match_terms("Claude Code and codex help", ["claude code", "codex", "c"])
    assert "claude code" in hits
    assert "codex" in hits
    assert "c" not in hits  # short tokens are ignored
    assert module._match_terms("scattered", ["cat"]) == []


def test_select_ranked_caps_per_channel_and_respects_top():
    module = _module("profile_ranked_brief_select")
    scored = [
        {"channel": "@a", "message_id": 1, "signal": 9.0, "posted_at": "x", "text": "", "url": "", "hits": []},
        {"channel": "@a", "message_id": 2, "signal": 8.0, "posted_at": "x", "text": "", "url": "", "hits": []},
        {"channel": "@a", "message_id": 3, "signal": 7.0, "posted_at": "x", "text": "", "url": "", "hits": []},
        {"channel": "@b", "message_id": 4, "signal": 6.0, "posted_at": "x", "text": "", "url": "", "hits": []},
    ]
    chosen = module.select_ranked(scored, top=3, per_channel=2)
    assert [c["message_id"] for c in chosen] == [1, 2, 4]


def test_build_persona_includes_projects_and_noise():
    module = _module("profile_ranked_brief_persona")
    profile = {
        "projects": [{"name": "ashishki/gdev-agent", "description": "agent runtime", "keywords": ["eval"]}],
        "project_terms": ["eval"],
        "channels": {"@data_secrets": 0.6},
        "noisy": ["@llm_under_hood"],
    }
    persona = module.build_persona(profile)
    assert "gdev-agent" in persona
    assert "llm_under_hood" in persona


def test_blocked_sources_are_configured():
    module = _module("profile_ranked_brief_blocked")
    assert "яндекс" in module.BLOCKED_SOURCE_TERMS
    assert "сбер" in module.BLOCKED_SOURCE_TERMS
