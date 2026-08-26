import { useEffect, useState } from "react";
import { api, type GoogleAuth } from "../api";

/**
 * Settings - an index of what can actually be configured, which today is one
 * thing.
 *
 * It exists because Google authorisation needed an address that says what it
 * is (`/settings/google`) rather than sitting at the top level beside `body`
 * and `health`, which are readings rather than settings.
 *
 * **Nothing here is clickable, and that is the same rule as everywhere else.**
 * A row is a readout: what the thing is, what state it is in, and the command
 * that opens or changes it. The palette is the only input in this interface
 * (`K`), and a settings page that quietly reintroduced a page full of controls
 * would be the "no buttons" rule broken in the one place it is most tempting.
 *
 * The list is built from live state, so a setting that is not wired is not
 * listed. Right now that means exactly one row.
 */

export function Settings() {
  const [google, setGoogle] = useState<GoogleAuth | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .google()
      .then((auth) => live && setGoogle(auth))
      .catch((cause) => live && setFailed((cause as Error).message));
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="settings">
      {failed && <p className="notice notice--bad">{failed}</p>}

      <section className="panel">
        <h2 className="panel__title">Google</h2>
        <div className="rows">
          <div className={google?.connected ? "row row--live" : "row"}>
            <span>calendar and mail</span>
            <b>{google ? google.state : "…"}</b>
          </div>
          <div className="row">
            <span>scopes</span>
            <b className="mono">
              {google?.scopes.length ? `${google.scopes.length} granted, read-only` : "none"}
            </b>
          </div>
        </div>
        {google && <p className="notice">{google.detail}</p>}
        {/* The command, named. Not a link - see the note at the top. */}
        <p className="settings__how mono">
          {google?.connected ? "disconnect google" : "connect google"} · K · /settings/google
        </p>
      </section>
    </div>
  );
}
