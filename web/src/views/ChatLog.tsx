import { useEffect, useState } from "react";
import { api, stamp, type ApiError, type Conversation } from "../api";
import { SESSION_ID, type Chat } from "../useChat";

/**
 * `chat` - what was **said**.
 *
 * Not a log, and no longer named like one. Her agent log, error log and gateway
 * log are read in a terminal (`open logs`, `open errors`, `open gateway`) and
 * nowhere else; this is the transcript, which is prose she wrote rather than
 * machine output, and that is why it is a view.
 *
 * Isabella stores no message content - the transcript lives in Hermes'
 * state.db and is read back at request time (core/transcript.py). So this page
 * shows two things at once and marks which is which:
 *
 *   · what has been said **in this browser session**, live, including a turn
 *     still in flight - it is not in the database until she answers
 *   · every conversation before it, out of Hermes, with the three things a bare
 *     transcript does not tell you: how long she took, what she was doing in
 *     the gap, and what it cost in tokens
 */

function Cost({ session }: { session: Conversation }) {
  const total = session.tokens.input + session.tokens.output;
  return (
    <div className="convo__cost mono">
      <span>{session.message_count} MSG</span>
      <span>{session.api_call_count} CALL{session.api_call_count === 1 ? "" : "S"}</span>
      <span>{total.toLocaleString()} TOK</span>
      {session.tool_call_count > 0 && <span>{session.tool_call_count} TOOL</span>}
      <span>{session.model ?? "unknown model"}</span>
    </div>
  );
}

export function ChatLog({ chat }: { chat: Chat }) {
  const [sessions, setSessions] = useState<Conversation[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .chatLog(20)
      .then((data) => live && setSessions(data.sessions))
      .catch((cause: ApiError) => live && setError(cause.message));
    return () => {
      live = false;
    };
    // Refetched when a turn settles: the reply is only in Hermes' database
    // once she has finished answering.
  }, [chat.waiting]);

  return (
    <div className="chatlog">
      {/* This session first, because it is the one still happening. It is
          labelled LIVE rather than dated - it has no row in the database yet
          and pretending otherwise would be the wrong kind of tidy. */}
      {chat.said.length > 0 && (
        <section className="convo convo--live">
          <header className="convo__head">
            <h2>this session</h2>
            <span className="badge badge--running">live</span>
            <span className="convo__id mono">{SESSION_ID}</span>
          </header>
          {chat.said.map((said, index) => (
            <article key={index} className={`turn turn--${said.who}`}>
              <div className="turn__who">{said.who === "owen" ? "you" : "isabella"}</div>
              <p>{said.text}</p>
              {said.seconds !== undefined && (
                <div className="turn__meta mono">
                  {said.seconds.toFixed(1)}s
                  {said.tokens !== undefined && ` · ${said.tokens} tok`}
                </div>
              )}
            </article>
          ))}
          {chat.waiting && <p className="notice">She is thinking. 8s for something simple, up to 90s for who she is.</p>}
          {chat.error && <p className="notice notice--bad">{chat.error}</p>}
        </section>
      )}

      {error && <p className="notice notice--bad">{error}</p>}
      {!sessions && !error && <p className="notice">Reading her transcript…</p>}
      {sessions?.length === 0 && <p className="notice">Nothing has been said to her yet.</p>}

      {sessions
        // The live conversation is printed above, from memory. Printing it
        // again from the database would show every turn twice.
        ?.filter((session) => session.id !== SESSION_ID)
        .map((session) => (
          <section className="convo" key={session.id}>
            <header className="convo__head">
              <h2>{session.title}</h2>
              <span className="convo__when mono">
                {session.last_activity_at ? stamp(session.last_activity_at) : "—"}
              </span>
              <span className="convo__id mono">{session.source}</span>
            </header>
            <Cost session={session} />

            {session.turns.length === 0 ? (
              // A session row with no messages is a fact about the session -
              // usually one that failed before anything was said.
              <p className="notice">Nothing was said in this one.</p>
            ) : (
              session.turns.map((turn) => (
                <article key={turn.id} className={`turn turn--${turn.who}`}>
                  <div className="turn__who">{turn.who === "owen" ? "you" : "isabella"}</div>
                  {turn.text ? (
                    <p>{turn.text}</p>
                  ) : (
                    <p className="turn__empty">(nothing came back)</p>
                  )}
                  {turn.note && <div className="turn__meta mono">{turn.note}</div>}
                </article>
              ))
            )}
          </section>
        ))}
    </div>
  );
}
