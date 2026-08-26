/**
 * The only place the UI knows an endpoint exists.
 *
 * Every call goes to Isabella's API on loopback, never to Hermes directly:
 * the Hermes key is hers and stays server-side. Nothing here holds a
 * credential, and nothing here should ever need one.
 */

import type { MindSnapshot } from "./lib/mind";

export type { MindSnapshot } from "./lib/mind";

export type Run = {
  id: number;
  trigger_id: string;
  job_id: string | null;
  source: string;
  started_at: string;
  finished_at: string | null;
  outcome: "ok" | "error" | "running" | "unknown" | string;
  detail: string | null;
  execution_id: string | null;
  /** What she actually said, read from Hermes' cron output. Null is normal:
   *  a run can fail before it speaks, and old runs predate local delivery. */
  briefing: string | null;
};

export type Trigger = {
  id: string;
  enabled: boolean;
  schedule: string;
  timezone?: string;
  paused?: boolean;
  job_id?: string | null;
  job_enabled?: boolean;
  last_status?: string | null;
  failure_streak?: number;
  reconciled?: boolean;
  next_run_at?: string | null;
  runs_today?: number;
  max_runs_per_day?: number;
  deliver?: string;
  script_install?: { drifted?: boolean; detail?: string } | null;
  [key: string]: unknown;
};

export type GoogleAuth = {
  connected: boolean;
  /** connected · partial · absent · corrupt · client_disabled · no_client_secret · unavailable */
  state: string;
  detail: string;
  scopes: string[];
};

export type DesktopTarget = {
  name: string;
  summary: string;
  exists: boolean;
  available: boolean;
  detail: string;
  /** Whether a Terminal window of hers is on screen for this target right now.
   *  It is what decides whether the palette offers `open logs` or `close logs`. */
  open: boolean;
};

export type Runtime = {
  model: { name: string; max_tokens: number; window_note: string; timeout_s: number };
  hermes: { url: string; ok: boolean; detail: string };
  persona: { sha256: string; drifted: boolean; installed: boolean };
  storage: Record<string, number>;
  autonomy: { runs_today: number; timezone: string | null };
};

export type BodyLog = {
  available: boolean;
  detail: string;
  as_of: string;
  weight: { value: number | null; on: string | null };
  water: { used: number | null; goal: number | null; on: string | null };
  sleep: { hours: number | null; on: string | null };
  week: {
    key: string;
    logged: boolean;
    days: { n: number; name: string; on: string; done: number; total: number }[];
    /** Muscle groups a ticked exercise worked. Drives the figure. */
    worked: string[];
  };
  measurements: {
    on: string | null;
    areas: { area: string; left: number | null; right: number | null; gap: number | null; note: string }[];
  };
};

/** One turn of a conversation, read back out of Hermes' state.db. `seconds` is
 *  the real wait - her timestamp minus the question's - and `note` is what she
 *  was doing in it. */
export type Turn = {
  id: number;
  who: "owen" | "isabella";
  text: string;
  at: string | null;
  seconds: number | null;
  tokens: number | null;
  reasoned: boolean;
  reasoning_chars: number;
  finish_reason: string | null;
  tool: string | null;
  note: string;
};

export type Conversation = {
  id: string;
  source: string;
  title: string;
  model: string | null;
  started_at: string | null;
  last_activity_at: string | null;
  message_count: number;
  tool_call_count: number;
  api_call_count: number;
  tokens: { input: number; output: number; reasoning: number };
  turns: Turn[];
};

export type Health = {
  ok: boolean;
  hermes: { url: string; ok: boolean; detail: string };
  model: string;
  persona: { installed: boolean; drifted: boolean; detail: string; sha256: string };
};

/** Timestamps are the machine speaking: mono, sortable, unambiguous.
 *  `8/27/2026, 7:00:00 AM` is the wrong register for a dense row, and is
 *  ambiguous to half the world besides. */
export function stamp(iso: string): string {
  const at = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())} ` +
    `${pad(at.getHours())}:${pad(at.getMinutes())}`
  );
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
  }
}

// She reasons before she answers: 8s for a simple question, up to 90s for an
// identity one. A default fetch timeout would cut her off mid-thought and
// report it as a network failure, which is the wrong diagnosis entirely.
const REPLY_TIMEOUT_MS = 300_000;
const READ_TIMEOUT_MS = 30_000;

async function call<T>(path: string, init: RequestInit = {}, timeoutMs = READ_TIMEOUT_MS): Promise<T> {
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...init, signal: abort.signal });
  } catch {
    // Her API is loopback-only and started by hand. "Failed to fetch" almost
    // always means it isn't running, so say that instead.
    const reason = abort.signal.aborted ? "took too long to answer" : "is not running";
    throw new ApiError(`Isabella's API ${reason} (localhost:8000).`, 0);
  } finally {
    clearTimeout(timer);
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    // /health answers 503 with a full body; the trigger routes answer
    // {error, detail}. Both are information, not noise - surface them.
    if (body && typeof body === "object" && "error" in body) {
      const payload = body as { error: string; detail?: string };
      throw new ApiError(payload.detail || payload.error, response.status, payload.error);
    }
    throw new ApiError(`HTTP ${response.status}`, response.status);
  }
  return body as T;
}

export const api = {
  health: () => call<Health>("/health"),

  runs: (limit = 20) => call<{ runs: Run[] }>(`/runs?limit=${limit}`),

  triggers: () => call<{ triggers: Trigger[] }>("/triggers"),

  pause: (id: string) => call<unknown>(`/triggers/${id}/pause`, { method: "POST" }),
  resume: (id: string) => call<unknown>(`/triggers/${id}/resume`, { method: "POST" }),
  fire: (id: string) => call<unknown>(`/triggers/${id}/run`, { method: "POST" }),

  google: () => call<GoogleAuth>("/google"),

  // Consent talks to Google, so it gets the long timeout too.
  googleConnect: () =>
    call<{ auth_url: string }>("/google/connect", { method: "POST" }, REPLY_TIMEOUT_MS),

  /** The pasted redirect URL is a live credential. It goes straight to her API
   *  over loopback and is never kept in component state longer than the call. */
  googleComplete: (redirect: string) =>
    call<GoogleAuth>(
      "/google/complete",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ redirect }),
      },
      REPLY_TIMEOUT_MS,
    ),

  googleDisconnect: () =>
    call<GoogleAuth>("/google/disconnect", { method: "POST" }, REPLY_TIMEOUT_MS),

  desktop: () => call<{ targets: DesktopTarget[] }>("/desktop"),

  /** Opens Terminal.app on Owen's machine. `name` selects a command that is a
   *  constant on the server - it is never assembled from anything sent here. */
  open: (name: string) =>
    call<{ opened: string; command: string; reused: boolean }>(`/desktop/open/${name}`, {
      method: "POST",
    }),

  /** Stops what is running in her Terminal windows and takes them off screen.
   *  Omit `name` for all of them. Never touches a window she did not open. */
  closeTerminal: (name?: string) =>
    call<{ closed: string[]; ended: number; stubborn: string[]; detail: string }>(
      `/desktop/close${name ? `/${name}` : ""}`,
      { method: "POST" },
    ),

  runtime: () => call<Runtime>("/runtime"),

  body: () => call<BodyLog>("/body"),

  /** The graph the brain draws. `live` is the session being spoken in and is
   *  the only thing that lights violet - pass it or nothing is lit, which is
   *  the truth when nobody is talking to her. */
  mind: (live?: string) => call<MindSnapshot>(`/mind${live ? `?live=${encodeURIComponent(live)}` : ""}`),

  /** What was said. Read back from Hermes at request time; Isabella stores no
   *  message content of her own. There is no sibling call for her AGENT log:
   *  that is read in a terminal, through `open`. */
  chatLog: (limit = 12) => call<{ available: boolean; detail: string; sessions: Conversation[] }>(
    `/chat/log?limit=${limit}`,
  ),

  chat: (message: string, sessionId: string) =>
    call<{ reply: string; seconds: number; completion_tokens: number }>(
      "/chat",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionId, surface: "web" }),
      },
      REPLY_TIMEOUT_MS,
    ),
};
