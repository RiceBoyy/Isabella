"""Failures worth naming separately, because they need different responses."""


class HermesError(Exception):
    """Base for anything that went wrong talking to Hermes."""


class HermesUnreachable(HermesError):
    """The gateway is not answering. Usually: it is not running."""


class HermesAuthError(HermesError):
    """Rejected. API_SERVER_KEY is wrong or missing - it is required on loopback."""


class EmptyCompletion(HermesError):
    """Hermes returned success with no content.

    This is not a transport failure and it is not rare. qwen3 reasons before
    answering; if it exhausts max_tokens mid-thought, `content` comes back
    empty with finish_reason="length" and HTTP 200. Measured reasoning cost
    ranges from 128 to 2,055 words depending on the prompt.

    Raising rather than returning "" so it can never be mistaken for her
    choosing to say nothing.
    """

    def __init__(self, finish_reason: str | None, reasoning_words: int) -> None:
        self.finish_reason = finish_reason
        self.reasoning_words = reasoning_words
        super().__init__(
            f"empty content (finish_reason={finish_reason}, "
            f"~{reasoning_words} words of reasoning). "
            "The model ran out of room mid-thought; raise max_tokens."
        )
