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
    JobRejected,
)

# POST /api/jobs accepts exactly these. Not model, not enabled_toolsets, not
# workdir - cron/jobs.py::create_job takes them but the HTTP surface does not
# pass them through. Sending more is silently dropped, which is worse than an
# error, so the client sends only what lands.
JOB_CREATE_FIELDS = frozenset({"name", "schedule", "prompt", "deliver", "skills", "repeat"})

# PATCH's whitelist, from api_server.py::_UPDATE_ALLOWED_FIELDS.
JOB_UPDATE_FIELDS = JOB_CREATE_FIELDS | {"enabled", "skill"}


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

    # ------------------------------------------------------------------
    # Jobs. Isabella's trigger engine reconciles desired state into these;
    # Hermes' scheduler owns when they actually fire.
    # ------------------------------------------------------------------

    async def _job_request(self, method: str, path: str, json: dict | None = None) -> dict:
        try:
            r = await self._http.request(method, path, json=json)
        except httpx.RequestError as exc:
            raise HermesUnreachable(
                f"{self._cfg.hermes_base_url} is not answering ({exc.__class__.__name__}). "
                "Is her gateway running?"
            ) from exc

        if r.status_code == 401:
            raise HermesAuthError("Hermes rejected the API key.")
        if r.status_code == 404:
            return {}
        if r.status_code >= 400:
            # 424 is the one that matters: saved but not scheduled. It would
            # otherwise read as "created" and never fire.
            detail = r.json().get("error", r.text) if r.text else r.reason_phrase
            raise JobRejected(r.status_code, str(detail))
        return r.json()

    async def list_jobs(self, *, include_disabled: bool = True) -> list[dict]:
        """Disabled jobs are included by default, unlike Hermes' own default.

        `GET /api/jobs` hides disabled jobs unless asked. A reconciler that
        cannot see a paused job concludes it is missing and creates a second
        one - so pausing the briefing silently produced a duplicate that was
        not paused. Verified against the live gateway, not inferred.
        """
        query = "?include_disabled=true" if include_disabled else ""
        body = await self._job_request("GET", f"/api/jobs{query}")
        return body.get("jobs", [])

    async def create_job(self, payload: dict) -> dict:
        body = await self._job_request(
            "POST", "/api/jobs", {k: v for k, v in payload.items() if k in JOB_CREATE_FIELDS}
        )
        return body.get("job", {})

    async def update_job(self, job_id: str, payload: dict) -> dict:
        body = await self._job_request(
            "PATCH", f"/api/jobs/{job_id}",
            {k: v for k, v in payload.items() if k in JOB_UPDATE_FIELDS},
        )
        return body.get("job", {})

    async def delete_job(self, job_id: str) -> None:
        await self._job_request("DELETE", f"/api/jobs/{job_id}")

    async def pause_job(self, job_id: str) -> dict:
        body = await self._job_request("POST", f"/api/jobs/{job_id}/pause")
        return body.get("job", {})

    async def resume_job(self, job_id: str) -> dict:
        body = await self._job_request("POST", f"/api/jobs/{job_id}/resume")
        return body.get("job", {})

    async def run_job(self, job_id: str) -> dict:
        body = await self._job_request("POST", f"/api/jobs/{job_id}/run")
        return body.get("job", {})
