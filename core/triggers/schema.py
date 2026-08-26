"""What a trigger definition is allowed to say.

Strict on purpose: `extra="forbid"` means a typo in a YAML key is a startup
error, not a guardrail that silently didn't apply. A trigger that can act
unprompted is the wrong place to be forgiving about spelling.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# Hermes rejects longer ones at POST /api/jobs; catch it here instead of
# discovering it at reconcile time.
MAX_PROMPT_CHARS = 5000
MAX_NAME_CHARS = 200


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Schedule(Strict):
    type: Literal["schedule"]
    cron: str
    timezone: str = "UTC"

    @field_validator("cron")
    @classmethod
    def five_fields(cls, v: str) -> str:
        if len(v.split()) != 5:
            raise ValueError(f"cron needs 5 fields, got {len(v.split())}: {v!r}")
        return v


class Condition(Strict):
    weekdays: list[str] | None = None

    @field_validator("weekdays")
    @classmethod
    def known_days(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        bad = [d for d in v if d.lower() not in WEEKDAYS]
        if bad:
            raise ValueError(f"unknown weekdays: {bad}")
        return [d.lower() for d in v]


class Action(Strict):
    type: Literal["prompt"]
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    skills: list[str] = Field(default_factory=list)

    # A pre-run script under HERMES_HOME/scripts/. Its stdout is injected into
    # the prompt as context before the model runs, so the model can be given
    # facts without being given tools. Decided 2026-08-23 - see ARCHITECTURE.md
    # §Pre-fetched context.
    #
    # Bare filename only: Hermes resolves it inside HERMES_HOME/scripts/ and
    # refuses anything that escapes, so a path here is a mistake, not a feature.
    script: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$", max_length=128
    )


class Deliver(Strict):
    channel: str = "local"


class Guardrails(Strict):
    """None of these have defaults that let you skip thinking about them.

    ARCHITECTURE.md: anything that can act unprompted carries a rate limit, a
    timeout, and a kill switch. Omitting one is a validation error.
    """

    max_runs_per_day: int = Field(ge=1, le=24)
    timeout_seconds: int = Field(ge=1, le=3600)
    on_failure: Literal["notify"]


class TriggerDef(Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$", max_length=MAX_NAME_CHARS)
    enabled: bool = True
    trigger: Schedule
    condition: Condition = Field(default_factory=Condition)
    action: Action
    deliver: Deliver = Field(default_factory=Deliver)
    guardrails: Guardrails

    def job_name(self) -> str:
        """The name this trigger owns at Hermes.

        Prefixed so reconciliation can tell her jobs apart from ones created by
        hand through `hermes cron` - which it must never delete.
        """
        return f"isabella:{self.id}"


def load_file(path: Path) -> TriggerDef:
    raw = yaml.safe_load(path.read_text())
    # Non-mappings fall through to pydantic, which reports the shape problem
    # with the same message shape as any other validation failure.
    try:
        return TriggerDef.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"{path.name}: {exc}") from exc


def load_dir(directory: Path) -> list[TriggerDef]:
    defs = [load_file(p) for p in sorted(directory.glob("*.yaml"))]
    seen: set[str] = set()
    for d in defs:
        if d.id in seen:
            raise ValueError(f"duplicate trigger id: {d.id}")
        seen.add(d.id)
    return defs
