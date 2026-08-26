"""Isabella's HTTP surface. Everything that reaches her goes through here."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core import body, desktop, mind, transcript
from core.config import settings
from core.desktop import DesktopError
from core.hermes import google_auth, outbox
from core.hermes.client import HermesClient
from core.hermes.errors import (
    EmptyCompletion,
    HermesAuthError,
    HermesError,
    HermesUnreachable,
    JobRejected,
)
from core.hermes.google_auth import GoogleAuthError
from core.persona import store
from core.triggers import store as run_store
from core.triggers.engine import Engine, ScriptJobNotCreatable, TimezoneMismatch

log = logging.getLogger("isabella")


class ChatIn(BaseModel):
    message: str = Field(min_length=1)

    # Continuity, chosen by the caller. The web UI holds one id per browser
    # session so a conversation is a conversation; curl omits it and gets the
    # stateless behaviour it had before.
    session_id: str | None = None
    surface: str = "api"


class ChatOut(BaseModel):
    reply: str
    prompt_tokens: int
    completion_tokens: int
    seconds: float


class GoogleCallbackIn(BaseModel):
    """What Google handed back, as pasted.

    The whole redirected URL or a bare code - both work. This is a live
    credential for the length of one exchange: it is never logged and never
    echoed back.
    """

    redirect: str = Field(min_length=1)


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

# The web UI in `web/` runs on Vite's dev server, which is a different origin.
# Loopback only, and named explicitly rather than "*": this API holds the
# Hermes key server-side and answers without authentication, so the set of
# pages allowed to call it is not something to leave open.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


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
        reply = await app.state.hermes.say(
            body.message, session_id=body.session_id, surface=body.surface
        )
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
            # `briefing` is read from Hermes' cron output at request time and
            # never stored - the runs table holds no message content, and that
            # is the whole reason there is only one memory here (DATA.md).
            "runs": outbox.attach(
                app.state.cfg, run_store.recent_runs(conn, trigger_id, min(limit, 200))
            ),
        })
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Google. A standing grant, so every route here is deliberate: one to look,
# one to start consent, one to finish it, one to end it.
#
# The token is written server-side into her HERMES_HOME, never into the
# browser. A cookie would be unreachable at 07:00, when the briefing actually
# runs and nobody is logged in. See core/hermes/google_auth.py.
# ----------------------------------------------------------------------


def _google(cfg) -> dict:
    state = google_auth.status(cfg)
    return {
        "connected": state.connected,
        "state": state.state,
        "detail": state.detail,
        "scopes": state.scopes,
    }


@app.get("/google")
async def google_status() -> JSONResponse:
    return JSONResponse(_google(app.state.cfg))


@app.post("/google/connect")
async def google_connect() -> JSONResponse:
    """Begin consent. Returns the URL to approve it at.

    Approving is Owen's to do in his own browser, under his own Google login -
    Isabella never handles the account password and never sees the consent
    screen.
    """
    try:
        return JSONResponse({"auth_url": google_auth.consent_url(app.state.cfg)})
    except GoogleAuthError as exc:
        log.error("google consent failed: %s", exc)
        return JSONResponse({"error": "google_consent", "detail": str(exc)}, 400)


@app.post("/google/complete")
async def google_complete(body: GoogleCallbackIn) -> JSONResponse:
    """Finish consent: exchange the code for a stored refresh token."""
    try:
        google_auth.complete(app.state.cfg, body.redirect)
    except GoogleAuthError as exc:
        # Deliberately logs the failure and not `body.redirect` - that string
        # is a live credential.
        log.error("google exchange failed: %s", exc)
        return JSONResponse({"error": "google_exchange", "detail": str(exc)}, 400)
    return JSONResponse(_google(app.state.cfg))


@app.post("/google/disconnect")
async def google_disconnect() -> JSONResponse:
    """Revoke the grant with Google and delete the token."""
    try:
        google_auth.disconnect(app.state.cfg)
    except GoogleAuthError as exc:
        log.error("google revoke failed: %s", exc)
        return JSONResponse({"error": "google_revoke", "detail": str(exc)}, 500)
    return JSONResponse(_google(app.state.cfg))


# ----------------------------------------------------------------------
# Desktop. The one path in Isabella that executes anything on the host.
#
# It opens Terminal.app on a NAMED target whose command is a constant in
# core/desktop.py. Nothing here composes a command, and nothing here routes
# through Hermes - her floor still has no terminal and no code_execution.
# See ARCHITECTURE.md §Opening a terminal.
# ----------------------------------------------------------------------


@app.get("/desktop")
async def desktop_targets() -> JSONResponse:
    return JSONResponse({"targets": desktop.targets(app.state.cfg)})


@app.post("/desktop/close")
async def desktop_close_all() -> JSONResponse:
    """Stop everything she has running in Terminal and take it off the screen.

    Only her own windows - they carry a custom title she stamps on them, and
    nothing without it is ever touched. See core/desktop.py for why this hides
    rather than closes.
    """
    try:
        return JSONResponse(desktop.close_target(app.state.cfg, None))
    except DesktopError as exc:
        return JSONResponse({"error": "desktop", "detail": str(exc)}, status_code=400)


@app.post("/desktop/close/{name}")
async def desktop_close(name: str) -> JSONResponse:
    """The same, for one named target. An unknown name is a 400, never a
    passthrough - the name selects from a constant table."""
    try:
        return JSONResponse(desktop.close_target(app.state.cfg, name))
    except DesktopError as exc:
        return JSONResponse({"error": "desktop", "detail": str(exc)}, status_code=400)


@app.post("/desktop/open/{name}")
async def desktop_open(name: str) -> JSONResponse:
    """Open a terminal on one target. `name` is looked up, never executed."""
    try:
        return JSONResponse(desktop.open_target(app.state.cfg, name))
    except DesktopError as exc:
        log.warning("desktop open refused: %s", exc)
        return JSONResponse({"error": "desktop_open", "detail": str(exc)}, 400)


# ----------------------------------------------------------------------
# Runtime. Her own body: what she is made of and what it costs.
#
# Every number here is one she actually has. No invented metrics and no
# meters whose length means nothing - the design system this UI follows
# allows a meter only when it shows a real quantity.
# ----------------------------------------------------------------------


def _size(path) -> int:
    try:
        if path.is_dir():
            return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return path.stat().st_size
    except OSError:
        return 0


@app.get("/runtime")
async def runtime() -> JSONResponse:
    cfg = app.state.cfg
    ok, detail = await app.state.hermes.healthy()
    persona = store.status(cfg)

    conn = run_store.connect(cfg)
    try:
        runs_today = sum(
            run_store.runs_today(conn, defn.id) for defn in app.state.engine.definitions()
        )
    finally:
        conn.close()

    return JSONResponse({
        "model": {
            "name": cfg.hermes_model,
            "max_tokens": cfg.max_tokens,
            # The declared window and the real one differ on purpose, and the
            # difference has bitten before: Ollama's /v1 ignores num_ctx, so the
            # Modelfile is the only channel and a stock model silently gives
            # 4096. The `-16k` in the name is the real number.
            "window_note": "real window comes from the Modelfile, not config",
            "timeout_s": cfg.request_timeout_s,
        },
        "hermes": {"url": cfg.hermes_base_url, "ok": ok, "detail": detail},
        "persona": {
            "sha256": persona.sha256[:12],
            "drifted": persona.drifted,
            "installed": persona.installed,
        },
        "storage": {
            # Hers is the big one, and that is the point: transcripts live in
            # Hermes, and Isabella's own database holds no message content.
            "hermes_state_db": _size(cfg.hermes_home / "state.db"),
            "isabella_db": _size(cfg.db_path),
            "cron_output": _size(cfg.cron_output_path),
            "logs": _size(cfg.hermes_home / "logs"),
        },
        "autonomy": {"runs_today": runs_today, "timezone": cfg.hermes_timezone},
    })


# ----------------------------------------------------------------------
# Body. Owen's, not hers - read out of the vault he already writes.
#
# Nothing here fills a gap: an unlogged measure comes back null and the view
# draws the absence. See core/body.py.
# ----------------------------------------------------------------------


@app.get("/body")
async def body_log() -> JSONResponse:
    return JSONResponse(body.read(app.state.cfg))


# ----------------------------------------------------------------------
# The mind, and the transcript.
#
# `/mind` is what she holds, as a graph. `/chat/log` is what was said. See
# core/mind.py for why the graph is built out of sessions and memories rather
# than out of a memory table Isabella must not have.
#
# There is deliberately NO `/log` endpoint. Her agent log is read in a terminal
# and nowhere else - `POST /desktop/open/logs`. See core/desktop.py.
# ----------------------------------------------------------------------


@app.get("/mind")
async def mind_graph(live: str | None = None) -> JSONResponse:
    """The graph the brain draws.

    `live` is the session id being spoken in, and it is the ONLY thing that
    lights violet - the conversation she is actually holding. Omitted, nothing
    is lit, which is the truth when nobody is talking to her.
    """
    return JSONResponse(mind.snapshot(app.state.cfg, live))


@app.get("/chat/log")
async def chat_log(limit: int = 12) -> JSONResponse:
    """What was said, with the wait and the token cost beside it.

    Read back out of Hermes' state.db at request time and never stored here -
    Isabella keeps no message content. See core/transcript.py.
    """
    return JSONResponse(transcript.read(app.state.cfg, limit=limit))
