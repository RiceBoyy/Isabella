import { useCallback, useEffect, useState } from "react";
import { api, ApiError, stamp, type Trigger } from "../api";

/**
 * What she does unprompted, and how to stop it.
 *
 * There are no buttons here - the actions are palette commands, so this view
 * names them. Pause is the kill switch ARCHITECTURE.md requires and it outranks
 * the YAML: a reconcile will not turn a paused job back on. A UI that made it
 * hard to find would be a regression dressed as a style choice, so it is
 * written out in full on the row it belongs to.
 */

export function Triggers() {
  const [triggers, setTriggers] = useState<Trigger[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setTriggers((await api.triggers()).triggers);
      setError(null);
    } catch (cause) {
      setError((cause as ApiError).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);


  if (error && !triggers) return <p className="notice notice--bad">{error}</p>;
  if (!triggers) return <p className="notice">Asking Hermes what is scheduled…</p>;

  return (
    <>
      {error && <p className="notice notice--bad">{error}</p>}
      <ul className="triggers">
        {triggers.map((trigger) => (
          <li key={trigger.id}>
            <header className="trigger__head">
              <span className="trigger__id">{trigger.id}</span>
              <span className={`badge badge--${trigger.paused ? "paused" : "ok"}`}>
                {trigger.paused ? "paused" : "active"}
              </span>
            </header>

            {/* Dense: mono rows, label left, value right. Bold foreground
                carries emphasis; the violet appears only on the next run,
                which is the one live thing here. */}
            <div className="rows">
              <div className="row">
                <span>schedule</span>
                <b>
                  {trigger.schedule} {trigger.timezone}
                </b>
              </div>
              <div className={trigger.paused ? "row" : "row row--live"}>
                <span>next run</span>
                <b>
                  {trigger.paused
                    ? "— paused"
                    : trigger.next_run_at
                      ? stamp(trigger.next_run_at)
                      : "not scheduled"}
                </b>
              </div>
              <div className="row">
                <span>today</span>
                <b>
                  {trigger.runs_today ?? 0} of {trigger.max_runs_per_day ?? "?"}
                </b>
              </div>
              <div className="row">
                <span>delivery</span>
                <b>{trigger.deliver}</b>
              </div>
            </div>

            <p className="hint">
              <code>{trigger.paused ? `resume ${trigger.id}` : `pause ${trigger.id}`}</code>
              {" · "}
              <code>run {trigger.id} now</code>
              {" — press K"}
            </p>

            {trigger.script_install?.drifted && (
              // The installed copy is what actually runs. If it differs from
              // the repo, the briefing is being built by unreviewed code -
              // worth shouting about, not a footnote.
              <p className="warn">
                The installed script has drifted from the repo. Hermes runs the installed
                copy: <code>cp scripts/{String(trigger.script)} ~/.hermes-isabella/scripts/</code>
              </p>
            )}

          </li>
        ))}
      </ul>
    </>
  );
}
