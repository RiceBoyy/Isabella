import { useCallback, useEffect, useState } from "react";
import { api, type Health, type Trigger } from "./api";
import { Palette, type Command } from "./Palette";
import { Body } from "./views/Body";
import type { LayerInfo } from "./components/Body3D";
import { SystemHealth } from "./views/Health";
import { Briefings } from "./views/Briefings";
import { ChatLog } from "./views/ChatLog";
import { Home } from "./views/Home";
import { Google } from "./views/Google";
import { Settings } from "./views/Settings";
import { Triggers } from "./views/Triggers";
import { useChat } from "./useChat";
import {
  close as closeWindow,
  isSpawned,
  navigate,
  open as openView,
  useOwnWindow,
  usePath,
  useTitle,
} from "./router";

/**
 * No buttons. Everything is a command — `K` opens the palette, the number keys
 * switch views. That is a deliberate step toward voice (M6): when speech
 * arrives it feeds the same command list rather than needing a second control
 * surface built beside this one.
 *
 * **Every view has an address, and home never gets replaced.** Picking a view
 * from home opens it in a window of its own — a window, not a tab, because a
 * tab behind a tab strip is still hidden and hidden was the complaint. From a
 * spawned window everything navigates in place, and `home` closes it. A window
 * that inherits a full-screen shape from home resizes itself on arrival, or it
 * would cover the thing it was opened to avoid covering. See `router.ts` —
 * hand-written, because no router ships any of that.
 *
 * The one thing this must not lose is the kill switch. `pause daily-briefing`
 * is a command, so it stays reachable — ARCHITECTURE.md requires that anything
 * acting unprompted can be stopped, and a UI with no way to stop it would be a
 * regression dressed as a style choice.
 *
 * `home` is first and is where a load lands: the brain, and her latest reply
 * under it. There is exactly ONE input in this interface and it is the palette:
 * a string that matches a command runs it, a string that matches nothing is
 * said to her. Home carried a second box for a day; two boxes on one screen
 * means working out the difference between them before typing anything, and
 * there is no difference worth learning.
 *
 * **No view here reads a log, and that is the decision.** Her agent log, her
 * error log and her gateway log are read in a terminal — `open logs`,
 * `open errors`, `open gateway`, colourised for a glance. A log view in the
 * browser was built and then removed: a scrolling log wants a terminal, and
 * two places to read the same file is one place too many.
 *
 * `chat` is not a log. It is the transcript — what was SAID — and it is a view
 * because it is prose she wrote, not machine output. Calling it "chat log" put
 * it in the same sentence as the agent log, which is exactly the confusion
 * worth avoiding.
 */

/* Every view has an address. `ROUTES` is the single table: the palette builds
   its view commands from it, the number keys index into it, and the renderer
   switches on it — so a path can only exist here, and adding one is one line
   rather than four edits that can disagree.

   The label IS the word. `chat` shows chat — no verb to remember, and it is the
   string voice will hand over unchanged at M6.

   `google` lives under `settings` because that is what it is. `body` and
   `health` stay at the top level because they are readings, not settings. */
const ROUTES = [
  { path: "/", label: "home" },
  { path: "/chat", label: "chat" },
  { path: "/briefings", label: "briefings" },
  { path: "/triggers", label: "triggers" },
  { path: "/body", label: "body" },
  { path: "/health", label: "health" },
  { path: "/settings", label: "settings" },
  { path: "/settings/google", label: "google" },
] as const;

function Presence() {
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    const check = () =>
      api
        .health()
        .then((state) => {
          setHealth(state);
          setDown(false);
        })
        .catch(() => setDown(true));
    void check();
    const timer = setInterval(check, 30_000);
    return () => clearInterval(timer);
  }, []);

  let mark = "○";
  let state = "…";
  let tone = "";

  if (down) [mark, state, tone] = ["×", "api down", "error"];
  else if (health && !health.hermes.ok) [mark, state, tone] = ["×", "hermes unreachable", "error"];
  else if (health?.persona.drifted) [mark, state, tone] = ["○", "persona drifted", "wait"];
  else if (health) [mark, state] = ["○", health.model];

  return (
    <div className={`presence ${tone ? `presence--${tone}` : ""}`}>
      <span className="presence__mark">{mark}</span>
      <span className="presence__state">{state}</span>
    </div>
  );
}

export function App() {
  const path = usePath();
  const [open, setOpen] = useState(false);
  const [commands, setCommands] = useState<Command[]>([]);
  const [said, setSaid] = useState<string | null>(null);
  /* Which anatomy layer the body shows, and the layers the atlas actually
     shipped. Built from the manifest rather than hardcoded, so a missing
     atlas offers no commands instead of commands that do nothing. */
  const [layer, setLayer] = useState<string | null>(null);
  const [layers, setLayers] = useState<LayerInfo[]>([]);
  // Bumped after any command that changes something, so the visible view
  // refetches rather than showing what was true before the command ran.
  const [tick, setTick] = useState(0);

  /* Talking to her, held once and shared. Home has the box; the chat log has
     the transcript. Two copies of this state would mean saying something on
     home and not seeing it in the log. */
  const bump = useCallback(() => setTick((n) => n + 1), []);
  const chat = useChat(bump);

  /* Name the window after what is in it. With views opening in windows of
     their own, a row of them all called "Isabella" is a row you have to click
     through to tell apart. */
  useTitle(ROUTES.find((route) => route.path === path)?.label ?? null);

  /* A window that came out full-screen because home was full-screen covers the
     thing it was opened to avoid covering. This puts it back. */
  useOwnWindow();

  const say = useCallback((line: string) => {
    setSaid(line);
    setTimeout(() => setSaid(null), 6000);
  }, []);

  /* Built fresh every time the palette opens, from what actually exists. A
     trigger that isn't there gets no command; a log file that isn't there is
     listed as missing rather than silently failing when picked. */
  const build = useCallback(async (): Promise<Command[]> => {
    /* The label IS the word. "body" shows body - no verb to remember, and it
       is the string voice will hand over unchanged when M6 arrives.

       The sub says the address AND what picking it will do with the window,
       because "opens a window" is a consequence that does not fit in the label
       and is the sort of thing that should never be a surprise. */
    const list: Command[] = ROUTES.map((route) => ({
      id: `view:${route.path}`,
      label: route.label,
      sub:
        route.path === path
          ? `${route.path} — you are here`
          : isSpawned() && route.path === "/"
            ? `${route.path} — closes this window · Q`
            : !isSpawned() && route.path !== "/"
              ? `${route.path} — opens a window`
              : route.path,
      run: () => openView(route.path),
    }));

    const [triggers, targets] = await Promise.allSettled([api.triggers(), api.desktop()]);

    if (triggers.status === "fulfilled") {
      for (const t of triggers.value.triggers as Trigger[]) {
        list.push(
          t.paused
            ? {
                id: `resume:${t.id}`,
                label: `resume ${t.id}`,
                sub: "lets it fire again",
                run: async () => {
                  await api.resume(t.id);
                  say(`${t.id} resumed`);
                  setTick((n) => n + 1);
                },
              }
            : {
                id: `pause:${t.id}`,
                label: `pause ${t.id}`,
                sub: "the kill switch — stops it at Hermes, instantly",
                run: async () => {
                  await api.pause(t.id);
                  say(`${t.id} paused`);
                  setTick((n) => n + 1);
                },
              },
        );
        list.push({
          id: `run:${t.id}`,
          label: `run ${t.id} now`,
          sub: "still subject to the daily rate limit",
          run: async () => {
            try {
              await api.fire(t.id);
              say(`${t.id} fired`);
            } catch {
              say(`${t.id} has already run its allowance today`);
            }
            setTick((n) => n + 1);
          },
        });
      }
    }

    if (targets.status === "fulfilled") {
      const onScreen = targets.value.targets.filter((t) => t.open);

      for (const target of targets.value.targets) {
        list.push({
          id: `open:${target.name}`,
          label: `open ${target.name}`,
          sub: !target.available
            ? target.detail
            : target.open
              ? `${target.summary} — already open, brings it back`
              : target.exists
                ? target.summary
                : `${target.summary} — nothing there yet`,
          run: async () => {
            try {
              const { reused } = await api.open(target.name);
              say(reused ? `${target.name} brought back` : `opened ${target.name} in Terminal`);
            } catch (cause) {
              say(String((cause as Error).message));
            }
          },
        });

        /* Offered only when there is actually a window to close - nothing is
           listed that is not wired. `Q` is the browser equivalent; a Terminal
           window cannot be reached by a keystroke from here, so this is the
           command that does the same job. */
        if (target.open) {
          list.push({
            id: `close:${target.name}`,
            label: `close ${target.name}`,
            sub: "stops it and takes the window off screen",
            run: async () => {
              try {
                const { detail } = await api.closeTerminal(target.name);
                // A window with something in it she did not start is left
                // open, and the reason is worth more than "closed".
                say(detail || `${target.name} closed`);
              } catch (cause) {
                say(String((cause as Error).message));
              }
            },
          });
        }
      }

      if (onScreen.length > 1) {
        list.push({
          id: "close:terminals",
          label: "close terminals",
          sub: `all ${onScreen.length} of hers — never one of yours`,
          run: async () => {
            try {
              const { closed, detail } = await api.closeTerminal();
              say(detail || `closed ${closed.length} of hers`);
            } catch (cause) {
              say(String((cause as Error).message));
            }
          },
        });
      }
    }

    for (const shipped of layers) {
      list.push({
        id: `layer:${shipped.id}`,
        label: shipped.id,
        sub: `show the body's ${shipped.label.toLowerCase()}`,
        run: () => {
          setLayer(shipped.id);
          openView("/body");
        },
      });
    }

    const google = await api.google().catch(() => null);
    if (google && !google.connected) {
      list.push({
        id: "google:connect",
        label: "connect google",
        sub: "read-only calendar and mail — opens Google's consent screen",
        run: async () => {
          openView("/settings/google");
          try {
            const { auth_url } = await api.googleConnect();
            // Opened from a keypress, so it is a user gesture and survives the
            // popup blocker. The consent screen is Google's and Owen's; she
            // never sees the account password.
            window.open(auth_url, "_blank", "noreferrer");
            say("consent opened — paste the localhost:1 address back here");
          } catch (cause) {
            say(String((cause as Error).message));
          }
        },
      });
    }
    if (google?.connected) {
      list.push({
        id: "google:disconnect",
        label: "disconnect google",
        sub: "revokes the grant — pick again to confirm",
        keepOpen: true,
        run: () => {
          setCommands((prior) => [
            {
              id: "google:disconnect!",
              label: "yes — revoke the google grant",
              sub: "she loses the calendar and the mailbox until you consent again",
              run: async () => {
                await api.googleDisconnect();
                say("google grant revoked");
                setTick((n) => n + 1);
              },
            },
            ...prior.filter((c) => c.id !== "google:disconnect"),
          ]);
        },
      });
    }

    return list;
  }, [say, layers, path]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const typing =
        event.target instanceof HTMLElement &&
        (event.target.tagName === "INPUT" || event.target.isContentEditable);

      if (event.key === "k" && !typing && !open) {
        event.preventDefault();
        setOpen(true);
        void build().then(setCommands);
        return;
      }
      if (typing || open) return;

      /* Arrows step through the anatomy layers, in the order the manifest
         ships them: skin, muscle, skeleton - outside inward, so right goes
         deeper and left comes back out. Only on the body, and only when the
         atlas actually shipped more than one, so the keys are never live with
         nothing to do. */
      if (path === "/body" && layers.length > 1) {
        const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
        if (step) {
          event.preventDefault();
          setLayer((current) => {
            const at = layers.findIndex((l) => l.id === current);
            const next = (at + step + layers.length) % layers.length;
            return layers[next].id;
          });
          return;
        }
      }

      /* `Q` hands the screen back. Every other way out of a view window is a
         keystroke, so the one that closes it should be too - otherwise this is
         the single place the interface makes you reach for the trackpad.

         On home it does nothing but say why. Home is the one that stays. */
      if (event.key === "q") {
        event.preventDefault();
        if (!closeWindow()) say("home is the one that stays - it does not close");
        return;
      }

      const index = Number(event.key) - 1;
      if (index >= 0 && index < ROUTES.length) openView(ROUTES[index].path);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [build, open, path, layers, say]);

  return (
    /* The body is a stage, not a column: it drops the reading measure and
       fills the viewport, with the header and footer as its only chrome. */
    <div className={path === "/body" || path === "/" ? "shell shell--stage" : "shell"}>
      <header className="shell__top">
        <span className="shell__name">Isabella</span>
        <Presence />
      </header>

      <main>
        {path === "/" && <Home chat={chat} tick={tick} />}
        {path === "/chat" && <ChatLog chat={chat} />}
        {path === "/briefings" && <Briefings key={`b${tick}`} />}
        {path === "/triggers" && <Triggers key={`t${tick}`} />}
        {path === "/body" && (
          <Body
            layer={layer}
            onLayers={(shipped, fallback) => {
              setLayers(shipped);
              setLayer((current) => current ?? fallback);
            }}
          />
        )}
        {path === "/health" && <SystemHealth key={`h${tick}`} />}
        {path === "/settings" && <Settings key={`s${tick}`} />}
        {path === "/settings/google" && <Google key={`g${tick}`} />}

        {/* An address that is not a view says so, and names the ones that are.
            Redirecting to home instead would hide the typo that got you here. */}
        {!ROUTES.some((route) => route.path === path) && (
          <p className="notice">
            Nothing lives at <code>{path}</code>. There is{" "}
            {ROUTES.map((route) => route.path).join(" · ")}.
          </p>
        )}
      </main>

      {/* One key, named in words. A row of view names would be a tab bar with
          the buttons taken off, and there is nothing here to navigate between
          that saying the word does not reach. */}
      <footer className="shell__foot">
        <span className="foot__keys">
          <b>K</b>
          {/* Named only where it does something. `K` is both the command
              surface and the way you talk to her, and a new pair of eyes has
              no way to guess the second half — so home says it. */}
          {path === "/" && " commands, or just say something"}
          {path !== "/" && isSpawned() && (
            <>
              {" · "}
              <b>Q</b> closes this window
            </>
          )}

          {/* Named only where it does something. The layer doubles as the
              readout - there is nowhere else that says which one you are
              looking at. */}
          {path === "/body" && layers.length > 1 && (
            <>
              {" · "}
              <b>←→</b> {layer}
            </>
          )}
        </span>
        {said && <span className="foot__said">{said}</span>}
      </footer>

      {/* One input in the whole interface. A string that matches a command runs
          it; a string that matches nothing is said to her. That is the same
          router voice hands a string to at M6, which is why there is no second
          box on home any more. */}
      {open && (
        <Palette
          commands={commands}
          busy={chat.waiting}
          onAsk={(text) => {
            if (chat.waiting) {
              say("she is still answering the last one");
              return;
            }
            /* In THIS window, always. The turn lives in this App's memory, so
               spending a new window on it would put the answer in a component
               nobody is looking at. Home and chat both show it where they
               are; anywhere else, move in place to the transcript. */
            if (path !== "/" && path !== "/chat") navigate("/chat");
            void chat.send(text);
          }}
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  );
}
