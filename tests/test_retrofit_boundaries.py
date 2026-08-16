from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_active_prm_has_no_report_imports():
    forbidden = ("output.weekly", "output.knowledge_atlas", "output.frontier", "output.mvp_weekly", "weekly_run_manifest")
    for path in (ROOT / "src" / "prm").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not any(marker in text for marker in forbidden), path


def test_active_bot_import_boundary():
    text = (ROOT / "src" / "bot" / "bot.py").read_text(encoding="utf-8")
    assert "from .legacy_handlers import" not in text
    assert "from .prm_handlers import" in text


def test_handlers_is_thin_facade():
    lines = (ROOT / "src" / "bot" / "handlers.py").read_text(encoding="utf-8").splitlines()
    assert len(lines) < 120
    assert (ROOT / "src" / "bot" / "legacy_handlers.py").exists()


def test_focused_tier_excludes_report_era():
    text = (ROOT / "tools" / "test_tiers.py").read_text(encoding="utf-8")
    active = text.split("LEGACY_COMPAT_TESTS", 1)[0]
    for name in ("test_weekly_brief_v3.py", "test_knowledge_library.py", "test_prm_release_gate.py"):
        assert name not in active


def test_eval_v2_uses_application_boundary():
    text = (ROOT / "tools" / "prm_qa_eval_v2.py").read_text(encoding="utf-8")
    assert "from prm.application import PersonalResearchAssistant" in text
    assert "from bot.handlers import _run_prm_auto_message_once" not in text
