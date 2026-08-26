"""Runtime settings. Everything that varies by host comes from the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
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

    # Everything of hers - config, state, transcripts, cron output, the
    # installed scripts - lives under one root. Named once here so the literal
    # is not repeated per path; the paths below derive from it unless the
    # environment sets them explicitly.
    hermes_home: Path = Path.home() / ".hermes-isabella"

    db_path: Path = REPO_ROOT / "data" / "isabella.db"
    triggers_path: Path = REPO_ROOT / "triggers"

    # Pre-run scripts. The repo is the source of truth; Hermes only ever runs
    # the installed copy, so the two are compared rather than assumed equal.
    scripts_path: Path = REPO_ROOT / "scripts"
    hermes_scripts_path: Path = Path.home() / ".hermes-isabella" / "scripts"

    # Where `deliver: local` puts a cron job's output: one markdown file per
    # run under `<job_id>/<local timestamp>.md`. The jobs API does not carry
    # the text of what a job produced, so this directory is the only place a
    # delivered briefing can be read back from. See ARCHITECTURE.md.
    cron_output_path: Path = Path.home() / ".hermes-isabella" / "cron" / "output"

    # Hermes resolves ONE timezone for the whole instance - there is no
    # per-job timezone (hermes_time.py). A trigger declaring a timezone is
    # asserting this value; reconcile refuses on mismatch rather than
    # firing at the wrong hour every day.
    hermes_timezone: str | None = None
    persona_path: Path = REPO_ROOT / "Personality" / "compiled" / "core.md"

    # Owen's notes. Read-only, and only `Personal/Body` is ever touched - the
    # body view has no other source, because a Mac has no Health database.
    vault_path: Path = Path.home() / "Projects" / "vault"

    # Hermes' own interpreter. `HERMES_HOME` redirects state only - the program
    # is a single shared install, and its venv is where the skills' Google
    # dependencies actually live. Running setup.py with anything else fails on
    # the import rather than on anything informative.
    hermes_python: Path = Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python"

    # Where Hermes reads her identity from. The persona is installed here, not
    # sent as a system message - sending one stacks a second identity on top.
    soul_path: Path = Path.home() / ".hermes-isabella" / "SOUL.md"

    @model_validator(mode="after")
    def _derive_from_hermes_home(self) -> "Settings":
        """Re-root the instance paths when HERMES_HOME is not the default.

        Only paths the environment did not set explicitly - an explicit value
        is a deliberate override and outranks the derivation.
        """
        derived = {
            "hermes_scripts_path": self.hermes_home / "scripts",
            "cron_output_path": self.hermes_home / "cron" / "output",
            "soul_path": self.hermes_home / "SOUL.md",
        }
        for field, value in derived.items():
            if field not in self.model_fields_set:
                setattr(self, field, value)
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
