import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type GoogleAuth } from "../api";

/**
 * Connecting her to Google. No buttons: `connect google` in the palette gets
 * the consent link and opens it, and this view is where the redirect comes
 * back — one input, submitted with Enter.
 *
 * Not a login. Nothing signs anyone into this page and no token is kept in the
 * browser: the grant is a refresh token written server-side into her
 * HERMES_HOME, because the briefing fires at 07:00 with no browser open and
 * nobody logged in.
 */

const SCOPES: Record<string, string> = {
  "https://www.googleapis.com/auth/gmail.readonly": "read your mail",
  "https://www.googleapis.com/auth/calendar.readonly": "read your calendar",
};

export function Google() {
  const [auth, setAuth] = useState<GoogleAuth | null>(null);
  const [paste, setPaste] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setAuth(await api.google());
    } catch (cause) {
      setError((cause as ApiError).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function complete(event: React.FormEvent) {
    event.preventDefault();
    if (!paste.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      setAuth(await api.googleComplete(paste));
      setPaste("");
    } catch (cause) {
      setError((cause as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  if (!auth && !error) return <p className="notice">Checking her Google connection…</p>;
  const connected = auth?.connected ?? false;

  return (
    <div className="panels panels--one">
      <section className="panel">
        <h2 className="panel__title">Google</h2>

        {error && <p className="notice notice--bad">{error}</p>}

        {connected ? (
          <>
            <div className="rows">
              {(auth?.scopes ?? []).map((scope) => (
                <div className="row" key={scope}>
                  <span>{SCOPES[scope] ?? scope}</span>
                  <b>read-only</b>
                </div>
              ))}
              <div className="row">
                <span>grant</span>
                <b>stored on this machine, valid until revoked</b>
              </div>
            </div>
            {auth?.state === "partial" && (
              <p className="warn">
                A permission was deselected at the consent screen, so part of the briefing
                will still report a blind spot. {auth.detail}
              </p>
            )}
            <p className="notice">
              <code>disconnect google</code> in the palette revokes it.
            </p>
          </>
        ) : auth?.state === "no_client_secret" || auth?.state === "unavailable" ? (
          <p className="notice notice--bad">{auth.detail}</p>
        ) : (
          <>
            <p className="prose">
              She has no access to your calendar or mail, so the briefing reports the blind
              spot rather than inventing a day. Connecting grants two read-only permissions —
              she cannot send, delete, or change anything.
            </p>
            <ol className="steps">
              <li>
                <span className="steps__n">1</span>
                <div className="steps__body">
                  Say <code>connect google</code> — the palette opens Google's consent screen.
                </div>
              </li>
              <li>
                <span className="steps__n">2</span>
                <div className="steps__body">
                  The browser then fails to load <code>localhost:1</code>. That is expected —
                  it means Google handed the code back. Copy the whole address.
                </div>
              </li>
              <li>
                <span className="steps__n">3</span>
                <div className="steps__body">
                  <form className="paste" onSubmit={complete}>
                    <input
                      value={paste}
                      onChange={(event) => setPaste(event.target.value)}
                      placeholder={busy ? "connecting…" : "paste it here, then enter"}
                      disabled={busy}
                    />
                  </form>
                </div>
              </li>
            </ol>
          </>
        )}
      </section>
    </div>
  );
}
