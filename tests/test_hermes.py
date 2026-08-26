"""The error paths matter more than the happy path here.

Empty completions are the documented qwen3 failure mode and must never be
mistaken for her choosing to say nothing.
"""

import httpx
import pytest

from core.config import Settings
from core.hermes.client import HermesClient
from core.hermes.errors import EmptyCompletion, HermesAuthError, HermesUnreachable


def _client(handler) -> HermesClient:
    cfg = Settings(hermes_api_key="test-key")
    c = HermesClient(cfg)
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=cfg.hermes_base_url
    )
    return c


def _completion(content, finish="stop", reasoning=""):
    return {
        "choices": [{"message": {"content": content, "reasoning": reasoning},
                     "finish_reason": finish}],
        "usage": {"prompt_tokens": 1930, "completion_tokens": 267},
    }


@pytest.mark.asyncio
async def test_reply_is_returned():
    c = _client(lambda r: httpx.Response(200, json=_completion("I'm here.")))
    reply = await c.say("Hello?")
    assert reply.text == "I'm here."
    assert reply.prompt_tokens == 1930


@pytest.mark.asyncio
async def test_empty_content_raises_not_returns_blank():
    """HTTP 200 with empty content = model ran out of room mid-thought."""
    c = _client(
        lambda r: httpx.Response(200, json=_completion("", "length", "word " * 2055))
    )
    with pytest.raises(EmptyCompletion) as exc:
        await c.say("who are you?")
    assert exc.value.finish_reason == "length"
    assert exc.value.reasoning_words == 2055


@pytest.mark.asyncio
async def test_whitespace_only_is_also_empty():
    c = _client(lambda r: httpx.Response(200, json=_completion("   \n  ")))
    with pytest.raises(EmptyCompletion):
        await c.say("hi")


@pytest.mark.asyncio
async def test_401_names_the_key():
    c = _client(lambda r: httpx.Response(401, json={}))
    with pytest.raises(HermesAuthError):
        await c.say("hi")


@pytest.mark.asyncio
async def test_gateway_down_is_a_clean_error():
    def down(request):
        raise httpx.ConnectError("connection refused")

    c = _client(down)
    with pytest.raises(HermesUnreachable, match="gateway running"):
        await c.say("hi")


@pytest.mark.asyncio
async def test_no_system_message_is_sent():
    """Her identity lives in SOUL.md. Sending a system prompt stacks a second one."""
    seen = {}

    def capture(request):
        seen.update(__import__("json").loads(request.content))
        return httpx.Response(200, json=_completion("ok"))

    c = _client(capture)
    await c.say("hi")
    assert [m["role"] for m in seen["messages"]] == ["user"]


@pytest.mark.asyncio
async def test_list_jobs_asks_for_disabled_ones():
    """Hermes hides disabled jobs by default. A reconciler that cannot see a
    paused job creates a second one - which is exactly what happened."""
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"jobs": []})

    await _client(handler).list_jobs()
    assert "include_disabled=true" in seen["url"]
