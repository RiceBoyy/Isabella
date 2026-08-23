"""Isabella's HTTP surface. Everything that reaches her goes through here."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.config import settings
from core.hermes.client import HermesClient
from core.hermes.errors import EmptyCompletion, HermesAuthError, HermesUnreachable
from core.persona import store

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
