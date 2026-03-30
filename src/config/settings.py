import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = "data/agent.db"
DEFAULT_MODEL_PROVIDER = "claude-haiku-4-5"
CHEAP_MODEL = os.environ.get("CHEAP_MODEL", "claude-haiku-4-5-20251001")
MID_MODEL = os.environ.get("MID_MODEL", "claude-sonnet-4-6")
STRONG_MODEL = os.environ.get("STRONG_MODEL", "claude-opus-4-6")
DEFAULT_TELEGRAM_SESSION_PATH = "/srv/openclaw-you/secrets/telegram.session"


def _resolve_path(value: str, base_dir: Path) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((base_dir / path).resolve())


@dataclass(frozen=True)
class Settings:
    db_path: str
    llm_api_key: str
    model_provider: str
    telegram_session_path: str


def load_settings() -> Settings:
    return Settings(
        db_path=_resolve_path(os.environ.get("AGENT_DB_PATH", DEFAULT_DB_PATH), PROJECT_ROOT),
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        model_provider=os.environ.get("MODEL_PROVIDER", DEFAULT_MODEL_PROVIDER),
        telegram_session_path=_resolve_path(
            os.environ.get("TELEGRAM_SESSION_PATH", DEFAULT_TELEGRAM_SESSION_PATH),
            PROJECT_ROOT,
        ),
    )
