from bot.runtime import BOT_RUNTIME_LEGACY, BOT_RUNTIME_PRM_ASSISTANT, normalize_bot_runtime_mode
from bot.prm_handlers import PRM_SAFE_COMMANDS


def test_runtime_mode_is_explicit():
    assert normalize_bot_runtime_mode("prm") == BOT_RUNTIME_PRM_ASSISTANT
    assert normalize_bot_runtime_mode("legacy") == BOT_RUNTIME_LEGACY


def test_active_registry_contains_only_prm_commands():
    assert "/weekly" not in PRM_SAFE_COMMANDS
    assert "/run_digest" not in PRM_SAFE_COMMANDS
    assert {"/auto", "/research", "/brief", "/chat"}.issubset(PRM_SAFE_COMMANDS)
