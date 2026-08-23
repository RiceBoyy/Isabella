"""The only module that speaks HTTP to Hermes.

Upstream is actively developed. When its API shifts, this file changes and
nothing else does.
"""

import time
from dataclasses import dataclass

import httpx

from core.config import Settings
from core.hermes.errors import (
    EmptyCompletion,
    HermesAuthError,
    HermesUnreachable,
)


@dataclass(slots=True)
class Reply:
    text: str
    finish_reason: str | None
    prompt_tokens: int
    completion_tokens: int
    seconds: float


class HermesClient:
    def __init__(self, cfg: Settings) -> None:
        self._cfg = cfg
        self._http = httpx.AsyncClient(
            base_url=cfg.hermes_base_url,
            timeout=cfg.request_timeout_s,
            headers={"Authorization": f"Bearer {cfg.hermes_api_key}"},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def healthy(self) -> tuple[bool, str]:
        """Is the gateway up and is our key accepted?

        Checks /v1/models rather than /health because /health does not
        authenticate, so it cannot tell us the key is wrong.
        """
        try:
            r = await self._http.get("/v1/models", timeout=10.0)
        except httpx.RequestError as exc:
            return False, f"unreachable at {self._cfg.hermes_base_url}: {exc.__class__.__name__}"
        if r.status_code == 401:
            return False, "reachable but rejected the API key"
        if r.status_code >= 400:
            return False, f"reachable but returned HTTP {r.status_code}"
        return True, "ok"

    async def say(self, message: str) -> Reply:
        """One turn.

        Deliberately sends no system message. Her identity is installed in
        ~/.hermes-isabella/SOUL.md; passing a system prompt here stacks a
        second identity on top of it and the model burns reasoning tokens
        reconciling them.
        """
        payload = {
            "model": self._cfg.hermes_model,
            "messages": [{"role": "user", "content": message}],
            "max_tokens": self._cfg.max_tokens,
        }
        started = time.perf_counter()
        try:
            r = await self._http.post("/v1/chat/completions", json=payload)
        except httpx.RequestError as exc:
            raise HermesUnreachable(
                f"{self._cfg.hermes_base_url} is not answering ({exc.__class__.__name__}). "
                "Is her gateway running?"
            ) from exc

        if r.status_code == 401:
            raise HermesAuthError("Hermes rejected the API key.")
        r.raise_for_status()

        body = r.json()
        choice = body["choices"][0]
        msg = choice.get("message", {})
        text = (msg.get("content") or "").strip()
        usage = body.get("usage", {})

        if not text:
            raise EmptyCompletion(
                finish_reason=choice.get("finish_reason"),
                reasoning_words=len((msg.get("reasoning") or "").split()),
            )

        return Reply(
            text=text,
            finish_reason=choice.get("finish_reason"),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            seconds=time.perf_counter() - started,
        )
