import { useEffect, useState } from "react";
import { api, ApiError, type Runtime, type Trigger } from "../api";
import { Rings } from "../Rings";

/**
 * System health — hers. `body` is Owen's, and they are different views for the
 * good reason that they are different subjects.
 *
 * Every number here is one she actually holds. The meter rule holds too: an arc
 * or a bar is allowed only where it shows a real quantity against a real
 * budget. Today's runs against the daily allowance has one. Storage does not,
 * so storage is numbers.
 */

function kb(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="panel">
      <h2 className="panel__title">{title}</h2>
      <div className="rows">{children}</div>
    </section>
  );
}

function Row({ k, v, live }: { k: string; v: React.ReactNode; live?: boolean }) {
  return (
    <div className={live ? "row row--live" : "row"}>
      <span>{k}</span>
      <b>{v}</b>
    </div>
  );
}

export function SystemHealth() {
  const [it, setIt] = useState<Runtime | null>(null);
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const load = () =>
      api
        .runtime()
        .then((state) => live && setIt(state))
        .catch((cause: ApiError) => live && setError(cause.message));
    void load();
    // The allowance the ring draws is a real budget, and it lives on the
    // trigger rather than in the runtime snapshot.
    void api
      .triggers()
      .then((data) => live && setTriggers(data.triggers))
      .catch(() => undefined);
    const timer = setInterval(load, 15_000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, []);

  if (error) return <p className="notice notice--bad">{error}</p>;
  if (!it) return <p className="notice">Taking her own measurements…</p>;

  const allowance = it.autonomy.runs_today;
  const budget = triggers.reduce((sum, t) => sum + (t.max_runs_per_day ?? 0), 0);
  const state = !it.hermes.ok ? "error" : it.persona.drifted ? "wait" : "idle";

  return (
    <>
      <Rings
        state={state}
        used={allowance}
        budget={budget}
        caption={it.model.name}
        legend={
          budget > 0
            ? `${allowance} of ${budget} today`
            : it.hermes.ok
              ? "no trigger scheduled"
              : it.hermes.detail
        }
      />

      <div className="panels">
      <Panel title="Mind">
        <Row k="model" v={it.model.name} />
        <Row k="reply cap" v={`${it.model.max_tokens} tokens`} />
        {/* The declared window and the real one differ, and it has bitten
            before - Ollama's /v1 ignores num_ctx, so the Modelfile is the only
            channel that reaches it. */}
        <Row k="window" v={it.model.window_note} />
        <Row k="patience" v={`${it.model.timeout_s}s`} />
      </Panel>

      <Panel title="Pulse">
        <Row
          k="gateway"
          v={it.hermes.ok ? it.hermes.detail : it.hermes.detail}
          live={it.hermes.ok}
        />
        <Row k="at" v={it.hermes.url} />
        <Row k="timezone" v={it.autonomy.timezone ?? "unset"} />
        <Row k="fired today" v={allowance} live={allowance > 0} />
      </Panel>

      <Panel title="Identity">
        <Row k="soul" v={it.persona.installed ? "installed" : "missing"} />
        <Row k="sha256" v={it.persona.sha256} />
        <Row k="drift" v={it.persona.drifted ? "DRIFTED" : "none"} />
      </Panel>

      <Panel title="Memory on disk">
        {/* Hers is the large one on purpose: transcripts live in Hermes, and
            Isabella's own database holds no message content at all. */}
        <Row k="hermes state" v={kb(it.storage.hermes_state_db)} />
        <Row k="her own db" v={kb(it.storage.isabella_db)} />
        <Row k="briefings" v={kb(it.storage.cron_output)} />
        <Row k="logs" v={kb(it.storage.logs)} />
      </Panel>
      </div>
    </>
  );
}
