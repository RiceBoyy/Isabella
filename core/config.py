"""Runtime settings. Everything that varies by host comes from the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Her Hermes instance. NOT 8642 - that is a different agent on this machine.
    hermes_base_url: str = "http://127.0.0.1:8643"
    hermes_api_key: str = ""

    # Must be a -16k Modelfile build. Ollama's /v1 ignores request-level num_ctx,
    # so a stock model silently gives you 4096 and truncates. See HISTORY.md.
    hermes_model: str = "qwen3:4b-16k"

    # qwen3 reasons before answering and that reasoning counts against this cap.
    # 2048 clipped "who are you?" in testing.
    max_tokens: int = 3000
    request_timeout_s: float = 300.0

    db_path: Path = REPO_ROOT / "data" / "isabella.db"
    persona_path: Path = REPO_ROOT / "Personality" / "compiled" / "core.md"

    # Where Hermes reads her identity from. The persona is installed here, not
    # sent as a system message - sending one stacks a second identity on top.
    soul_path: Path = Path.home() / ".hermes-isabella" / "SOUL.md"


@lru_cache
def settings() -> Settings:
    return Settings()
