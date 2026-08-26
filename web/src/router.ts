import { useEffect, useState } from "react";

/**
 * Addresses, and which of them get a window of their own.
 *
 * Every view has a path, so a screen can be linked, bookmarked, reloaded and
 * gone back from. Before this the whole interface lived at `/` and a reload put
 * you back on home no matter what you were reading.
 *
 * **Home is never replaced.** Picking a view from home opens it in a window of
 * its own rather than navigating over the top of the brain — home is the screen
 * you leave up, and losing it to go and read the trigger list was the wrong
 * trade. A window, not a tab: a tab behind a tab strip is still hidden, and
 * hidden was the whole complaint. Everything else follows from that one rule:
 *
 *   · from HOME, a view opens in its own window. The window is NAMED, so
 *     picking `chat` twice reuses the chat window instead of opening a second.
 *   · from a SPAWNED window, navigation happens in place. That window is
 *     already not home, so replacing its contents hides nothing worth keeping.
 *   · from a spawned window, going `home` — or pressing `Q` — CLOSES it and
 *     leaves you back on the home window. `window.close()` works here precisely
 *     because it was opened by script — and it is the honest thing to do,
 *     because a second copy of home in a window called "chat" is worse than no
 *     window at all.
 *
 * A deep link opened by hand (`/chat` typed into the address bar) has no opener
 * and behaves like an ordinary page: everything navigates in place, including
 * home. Nothing here assumes it was spawned.
 *
 * **Hand-written, and about eighty lines of it.** `react-router` would be a
 * dependency for eight static paths with no params, no loaders and no nesting
 * beyond one level — CLAUDE.md says check before adding one, and this is what
 * checking looks like when the answer is no. It also would not have done the
 * window rule above, which is the part that matters here.
 *
 * The router does not own what a path *means*: `ROUTES` in App.tsx does. This
 * file knows how to read the address bar, how to change it, when to spend a
 * window on it, and how to hear the back button.
 */

const NAVIGATED = "isabella:navigate";

/** The current path, kept in sync with the address bar and the back button. */
export function usePath(): string {
  const [path, setPath] = useState(() => normalise(window.location.pathname));

  useEffect(() => {
    const onPop = () => setPath(normalise(window.location.pathname));
    window.addEventListener("popstate", onPop);
    // The same event `navigate` fires, so a programmatic move updates every
    // listener rather than only the component that triggered it.
    window.addEventListener(NAVIGATED, onPop);
    return () => {
      window.removeEventListener("popstate", onPop);
      window.removeEventListener(NAVIGATED, onPop);
    };
  }, []);

  return path;
}

/** Whether this window was opened by the home window. */
export const isSpawned = (): boolean => {
  try {
    return window.opener != null;
  } catch {
    // Cross-origin opener, which cannot happen here — but reading it is the
    // kind of thing that throws in a sandbox, and a router is not worth a
    // white screen.
    return false;
  }
};

/**
 * Go somewhere in THIS window, without a reload.
 *
 * Used where the destination has to share this window's memory — the live chat
 * turn lives in App state, so sending from `/triggers` has to land somewhere in
 * the same window or the answer arrives in a component nobody is looking at.
 */
export function navigate(path: string): void {
  const to = normalise(path);
  // Pushing the address you are already at would put a duplicate on the stack
  // and make `back` appear to do nothing the first time it is pressed.
  if (normalise(window.location.pathname) === to) return;
  window.history.pushState(null, "", to);
  window.dispatchEvent(new Event(NAVIGATED));
}

/**
 * Go somewhere, spending a window on it if that is what protects home.
 *
 * This is what the palette and the number keys call. It must stay reachable
 * synchronously from the keypress that triggered it — `window.open` after an
 * `await` is an unsolicited popup, and gets blocked.
 */
export function open(path: string): void {
  const to = normalise(path);
  if (normalise(window.location.pathname) === to) return;

  if (isSpawned()) {
    // Already not home. Going home means handing the screen back rather than
    // making a second one.
    if (to === "/") {
      close();
      return;
    }
    return navigate(to);
  }

  if (to === "/") return navigate(to);

  // Named, so the second `chat` reuses the first chat window. Not `noopener`:
  // the opener is exactly what lets that window know it can close itself.
  const child = window.open(to, `isabella${to}`, chrome());
  // Best effort from this side. The child corrects itself too — see
  // `useOwnWindow`, and the note there about why one of the two is not enough.
  fit(child, window);
}

/** How big the spawned window should be, and where it should sit.
 *
 *  Offset from the window that opened it rather than centred on the screen: a
 *  new window landing exactly on top of home looks like home was replaced,
 *  which is the one thing this whole rule is here to prevent. Clamped so a home
 *  window near an edge does not push its child off the display.
 */
function box(from: Window): { width: number; height: number; left: number; top: number } {
  const { availWidth, availHeight } = window.screen;
  const width = Math.min(1280, Math.round(availWidth * 0.72));
  const height = Math.min(900, Math.round(availHeight * 0.86));

  let fromX = 0;
  let fromY = 0;
  try {
    fromX = from.screenX;
    fromY = from.screenY;
  } catch {
    // A cross-origin opener, which cannot happen here. Falling back to the
    // top-left corner is better than not opening the window.
  }

  return {
    width,
    height,
    left: Math.max(0, Math.min(availWidth - width, fromX + 48)),
    top: Math.max(0, Math.min(availHeight - height, fromY + 48)),
  };
}

/**
 * The feature string.
 *
 * Passing any features at all is what makes the browser open a WINDOW rather
 * than a tab — that is the whole reason this function exists, and why it must
 * never return an empty string.
 */
function chrome(): string {
  const { width, height, left, top } = box(window);
  return `popup=yes,width=${width},height=${height},left=${left},top=${top}`;
}

/** Put a window where it was asked to go. Never throws. */
function fit(target: Window | null, from: Window): void {
  if (!target) return;
  const { width, height, left, top } = box(from);
  try {
    target.resizeTo(width, height);
    target.moveTo(left, top);
  } catch {
    // Some window states refuse to be moved. A window in the wrong place is
    // still a window; a white screen is not.
  }
}

/* Set once by a spawned window after it has sized itself, so a reload does not
   undo a size the person chose by hand afterwards. Home never sets it, and a
   spawned window inherits a COPY of home's sessionStorage — so the key is
   reliably absent on the first load of a new window, which is exactly when it
   needs to act. */
const SIZED = "isabella:sized";

/**
 * A spawned window, correcting its own size.
 *
 * The feature string is a request, not an instruction. When the window that
 * opened it is maximised or full-screen, the browser hands the new window the
 * same shape — which covers home completely and defeats the entire point of
 * spending a window on the view. So the child checks its own dimensions on
 * first load and, if it came out covering the screen, puts itself back to the
 * size that was asked for.
 *
 * Why the child and not only the opener: `resizeTo` from the opener runs before
 * the new window has laid anything out, and is the call browsers are most
 * willing to ignore. Doing it here runs in the window's own context, after it
 * exists. Both are done, because either one alone leaves a case uncovered.
 *
 * **Only when it came out oversized, and only once.** A window the person
 * maximised on purpose is left alone, and a reload never re-shrinks it.
 *
 * The one case this cannot fix is macOS native full-screen: the browser opens
 * the new window in its own Space, and no script can pull it back out. It is
 * still resized, so it is a normal window when you leave that Space.
 */
export function useOwnWindow(): void {
  useEffect(() => {
    if (!isSpawned()) return;

    try {
      if (sessionStorage.getItem(SIZED) === "1") return;
      sessionStorage.setItem(SIZED, "1");
    } catch {
      // Private mode, or storage refused. Sizing once too often is a much
      // smaller problem than not sizing at all.
    }

    const { availWidth, availHeight } = window.screen;
    const covering =
      window.outerWidth >= availWidth * 0.94 || window.outerHeight >= availHeight * 0.94;
    if (!covering) return;

    fit(window, (window.opener as Window | null) ?? window);
  }, []);
}

/**
 * Hand the screen back: close this window and leave the home window in front.
 *
 * `Q` is bound to this, and so is picking `home` from a spawned window - they
 * are the same act, and a window that has to be closed with the mouse when
 * everything else is a keystroke is the one place the interface would make you
 * reach for the trackpad.
 *
 * On the home window this does nothing on purpose. Home is the one that stays -
 * it was never opened by script, so the browser would refuse anyway, and
 * closing it is the opposite of what the windows are for.
 */
export function close(): boolean {
  if (!isSpawned()) return false;

  window.close();
  /* Chrome refuses to close a window it did not open, and a reloaded one can
     lose its opener. If we are still here a moment later, show home rather than
     having done nothing at all. */
  setTimeout(() => navigate("/"), 150);
  return true;
}

/** Name the window after what is in it, so a row of them can be told apart. */
export function useTitle(label: string | null): void {
  useEffect(() => {
    document.title = label && label !== "home" ? `Isabella · ${label}` : "Isabella";
  }, [label]);
}

/** One shape for a path, so `/chat/` and `/chat` are not two different views. */
function normalise(path: string): string {
  if (!path.startsWith("/")) path = `/${path}`;
  const trimmed = path.replace(/\/+$/, "");
  return trimmed || "/";
}
