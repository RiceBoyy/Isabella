import { useCallback, useState } from "react";
import { api, ApiError } from "./api";

/**
 * Talking to her, held in one place.
 *
 * It moved out of the Chat view because two screens now need it: home has the
 * box you type into, and the chat log has the transcript. Two copies of this
 * state would mean saying something on home and not seeing it in the log,
 * which is the sort of split that makes a log untrustworthy.
 *
 * Two things this has to stay honest about, both from CLAUDE.md:
 *
 * 1. **She is slow, and it is not a hang.** qwen3 reasons before it speaks -
 *    8s for something simple, up to 90s for a question about who she is.
 *    Nothing here times out early and nothing pretends to know how long she
 *    will take.
 * 2. **Empty content is a real error.** Reasoning counts against max_tokens;
 *    starved, the reply comes back empty with finish_reason=length. The API
 *    reports `empty_completion` and this says what it means rather than
 *    showing a blank turn.
 */

export type Said = {
  who: "owen" | "isabella";
  text: string;
  seconds?: number;
  tokens?: number;
};

/* One conversation per page load, and this id is Hermes' session id - the same
   string the transcript in state.db is keyed by. That is what lets home light
   the conversation you are actually in: `/mind?live=<this>`. */
export const SESSION_ID = `web-${crypto.randomUUID()}`;

export interface Chat {
  said: Said[];
  waiting: boolean;
  error: string | null;
  send: (message: string) => Promise<void>;
  /** Her most recent reply, for the one line home prints under the core. */
  last: Said | null;
}

export function useChat(onSettled?: () => void): Chat {
  const [said, setSaid] = useState<Said[]>([]);
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = useCallback(
    async (raw: string) => {
      const message = raw.trim();
      if (!message || waiting) return;

      setSaid((prior) => [...prior, { who: "owen", text: message }]);
      setError(null);
      setWaiting(true);
      try {
        const reply = await api.chat(message, SESSION_ID);
        setSaid((prior) => [
          ...prior,
          {
            who: "isabella",
            text: reply.reply,
            seconds: reply.seconds,
            tokens: reply.completion_tokens,
          },
        ]);
      } catch (cause) {
        const failure = cause as ApiError;
        setError(
          failure.code === "empty_completion"
            ? "She ran out of room mid-thought - the reasoning used the whole token budget, so nothing came back. Ask something shorter, or raise MAX_TOKENS."
            : failure.message,
        );
      } finally {
        setWaiting(false);
        // The turn is now in Hermes' state.db, so whatever reads it back - the
        // graph, the chat log - is a request behind until it refetches.
        onSettled?.();
      }
    },
    [waiting, onSettled],
  );

  const last = [...said].reverse().find((s) => s.who === "isabella") ?? null;

  return { said, waiting, error, send, last };
}
