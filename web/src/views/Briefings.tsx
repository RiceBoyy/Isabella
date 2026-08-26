import { useEffect, useState } from "react";
import { api, ApiError, type Run } from "../api";

/**
 * The reason this UI exists.
 *
 * The briefing has been composed and delivered every weekday morning to a file
 * nobody opens. This is the page that opens it.
 */

const WHEN = new Intl.DateTimeFormat(undefined, {
  weekday: "long",
  day: "numeric",
  month: "long",
  hour: "2-digit",
  minute: "2-digit",
});

function when(stamp: string | null): string {
  if (!stamp) return "unfinished";
  return WHEN.format(new Date(stamp));
}

function Outcome({ run }: { run: Run }) {
  return (
    <span className={`badge badge--${run.outcome}`} title={run.detail ?? undefined}>
      {run.outcome}
    </span>
  );
}

// Timestamps are the machine speaking, so they are mono - the split is who is
// speaking, not whether it is code.

export function Briefings() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .runs(30)
      .then((data) => live && setRuns(data.runs))
      .catch((cause: ApiError) => live && setError(cause.message));
    return () => {
      live = false;
    };
  }, []);

  if (error) return <p className="notice notice--bad">{error}</p>;
  if (!runs) return <p className="notice">Reading her ledger…</p>;
  if (runs.length === 0)
    return <p className="notice">Nothing has run yet. Her first briefing will land here.</p>;

  return (
    <ol className="briefings">
      {runs.map((run) => (
        <li key={run.id}>
          <header className="briefing__head">
            <h2 className="briefing__when">{when(run.finished_at ?? run.started_at)}</h2>
            <Outcome run={run} />
            <span className="briefing__who">
              {run.trigger_id} · {run.source}
            </span>
          </header>

          {run.briefing ? (
            <p className="briefing__text">{run.briefing}</p>
          ) : (
            // Deliberately not blank and not invented. A run with no text is a
            // fact about the run, and the page says which fact.
            <p className="notice">
              {run.outcome === "error"
                ? `No briefing - the run failed.${run.detail ? ` ${run.detail}` : ""}`
                : "No briefing recorded for this run."}
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}
