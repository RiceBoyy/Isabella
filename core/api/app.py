"""Isabella's HTTP surface. Everything that reaches her goes through here."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.config import settings
from core.hermes.client import HermesClient
from core.hermes.errors import (
    EmptyCompletion,
    HermesAuthError,
    HermesError,
    HermesUnreachable,
    JobRejected,
)
from core.persona import store
from core.triggers import store as run_store
from core.triggers.engine import Engine, ScriptJobNotCreatable, TimezoneMismatch

log = logging.getLogger("isabella")


class ChatIn(BaseModel):
    message: str = Field(min_length=1)


class ChatOut(BaseModel):
    reply: str
    prompt_tokens: int
    completion_tokens: int
    seconds: float


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = settings()
    app.state.cfg = cfg
    app.state.hermes = HermesClient(cfg)
    app.state.engine = Engine(cfg, app.state.hermes)

    # Parse the trigger files at boot. A malformed guardrail should stop her
    # starting, not surface the first morning something fires wrong.
    try:
        app.state.engine.definitions()
    except Exception as exc:
        log.error("trigger definitions are invalid: %s", exc)
        raise

    state = store.status(cfg)
    if state.drifted:
        log.warning("persona drift: %s", state.detail)
    yield
    await app.state.hermes.aclose()


app = FastAPI(title="Isabella", lifespan=lifespan)


@app.get("/health")
async def health() -> JSONResponse:
    cfg = app.state.cfg
    ok, detail = await app.state.hermes.healthy()
    persona = store.status(cfg)

    body = {
        "ok": ok and not persona.drifted,
        "hermes": {"url": cfg.hermes_base_url, "ok": ok, "detail": detail},
        "model": cfg.hermes_model,
        "persona": {
            "installed": persona.installed,
            "drifted": persona.drifted,
            "detail": persona.detail,
            "sha256": persona.sha256[:12],
        },
    }
    return JSONResponse(body, status_code=200 if body["ok"] else 503)


@app.post("/chat", response_model=ChatOut)
async def chat(body: ChatIn) -> ChatOut | JSONResponse:
    try:
        reply = await app.state.hermes.say(body.message)
    except HermesUnreachable as exc:
        return JSONResponse({"error": "hermes_unreachable", "detail": str(exc)}, 503)
    except HermesAuthError as exc:
        return JSONResponse({"error": "hermes_auth", "detail": str(exc)}, 502)
    except EmptyCompletion as exc:
        # Not a crash and not silence she chose. The model ran out of room.
        return JSONResponse(
            {
                "error": "empty_completion",
                "detail": str(exc),
                "finish_reason": exc.finish_reason,
                "reasoning_words": exc.reasoning_words,
            },
            502,
        )
    return ChatOut(
        reply=reply.text,
        prompt_tokens=reply.prompt_tokens,
        completion_tokens=reply.completion_tokens,
        seconds=round(reply.seconds, 1),
    )


# ----------------------------------------------------------------------
# Triggers. Isabella owns what should happen; Hermes owns when it fires.
# These endpoints push desired state and read back what Hermes actually has.
# ----------------------------------------------------------------------


def _trigger_error(exc: HermesError | TimezoneMismatch | ScriptJobNotCreatable) -> JSONResponse:
    if isinstance(exc, HermesUnreachable):
        return JSONResponse({"error": "hermes_unreachable", "detail": str(exc)}, 503)
    if isinstance(exc, HermesAuthError):
        return JSONResponse({"error": "hermes_auth", "detail": str(exc)}, 502)
    if isinstance(exc, TimezoneMismatch):
        return JSONResponse({"error": "timezone_mismatch", "detail": str(exc)}, 409)
    if isinstance(exc, ScriptJobNotCreatable):
        # 409, not 500: nothing is broken, there is a step to take.
        return JSONResponse({"error": "script_job_not_creatable", "detail": str(exc)}, 409)
    if isinstance(exc, JobRejected):
        # 424 from Hermes means saved-but-not-scheduled. Passing the status
        # through keeps that distinguishable from a plain bad payload.
        return JSONResponse({"error": "job_rejected", "detail": str(exc)}, 502)
    raise exc


@app.get("/triggers")
async def list_triggers() -> JSONResponse:
    try:
        return JSONResponse({"triggers": await app.state.engine.status()})
    except (HermesError, TimezoneMismatch, ScriptJobNotCreatable) as exc:
        return _trigger_error(exc)


@app.post("/triggers/reconcile")
async def reconcile(dry_run: bool = False) -> JSONResponse:
    """Push the YAML into Hermes. Idempotent: twice changes nothing."""
    try:
        plan = await app.state.engine.reconcile(dry_run=dry_run)
    except ValueError as exc:
        return JSONResponse({"error": "invalid_trigger", "detail": str(exc)}, 400)
    except (HermesError, TimezoneMismatch, ScriptJobNotCreatable) as exc:
        return _trigger_error(exc)
    return JSONResponse({"dry_run": dry_run, **plan.as_dict()})


@app.post("/triggers/{trigger_id}/pause")
async def pause_trigger(trigger_id: str) -> JSONResponse:
    """The kill switch that works without a deploy. ROADMAP M2 requires this
    to stop a briefing instantly, and it stops it at Hermes - not here."""
    try:
        job = await app.state.engine.pause(trigger_id)
    except (HermesError, TimezoneMismatch, ScriptJobNotCreatable) as exc:
        return _trigger_error(exc)
    if job is None:
        return JSONResponse({"error": "not_found", "detail": trigger_id}, 404)
    return JSONResponse({"paused": trigger_id, "job": job})


@app.post("/triggers/{trigger_id}/resume")
async def resume_trigger(trigger_id: str) -> JSONResponse:
    try:
        job = await app.state.engine.resume(trigger_id)
    except (HermesError, TimezoneMismatch, ScriptJobNotCreatable) as exc:
        return _trigger_error(exc)
    if job is None:
        return JSONResponse({"error": "not_found", "detail": trigger_id}, 404)
    return JSONResponse({"resumed": trigger_id, "job": job})


@app.post("/triggers/{trigger_id}/run")
async def run_trigger(trigger_id: str) -> JSONResponse:
    """Fire it now. Still subject to max_runs_per_day - a manual override that
    ignored the rate limit would make the limit advisory."""
    try:
        result = await app.state.engine.fire(trigger_id)
    except (HermesError, TimezoneMismatch, ScriptJobNotCreatable) as exc:
        return _trigger_error(exc)
    if result is None:
        return JSONResponse({"error": "not_found", "detail": trigger_id}, 404)
    if not result.get("ok"):
        return JSONResponse(result, 429)
    return JSONResponse(result)


@app.get("/runs")
async def list_runs(trigger_id: str | None = None, limit: int = 20) -> JSONResponse:
    """Her audit trail, including runs she never asked for.

    Syncs from Hermes first. Cron fires without Isabella in the path, so a
    scheduled briefing exists only as a Hermes execution record until this
    folds it in. If Hermes is down, serve what she already has rather than
    failing the read - a stale ledger beats no ledger.
    """
    synced = None
    try:
        synced = await app.state.engine.sync_runs()
    except (HermesError, TimezoneMismatch) as exc:
        log.warning("run sync skipped: %s", exc)

    conn = run_store.connect(app.state.cfg)
    try:
        return JSONResponse({
            "synced": synced,
            "runs": run_store.recent_runs(conn, trigger_id, min(limit, 200)),
        })
    finally:
        conn.close()
