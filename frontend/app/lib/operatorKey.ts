import { useSyncExternalStore } from "react";

// Runtime storage for the operator key.
//
// This replaces `import.meta.env.VITE_OPERATOR_API_KEY`, which Vite substituted as a
// literal at build time — the key ended up verbatim in `build/client/assets/api-*.js`,
// a public asset served to every visitor of every page including the prospect-facing
// reports. Gating an "operator-only" screen on a string that ships to everyone is not
// access control. The key now never enters the bundle; the operator pastes it once per
// browser session.

const STORAGE_KEY = "tradual_operator_key";

const listeners = new Set<() => void>();

function notify() {
  for (const listener of listeners) listener();
}

export function getOperatorKey(): string {
  // `ssr: true` in react-router.config.ts means this module is evaluated on the server
  // too, where sessionStorage doesn't exist. The try/catch is separate: sessionStorage
  // access *throws* (rather than returning null) under some privacy settings.
  if (typeof window === "undefined") return "";
  try {
    return window.sessionStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setOperatorKey(key: string): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, key);
  } catch {
    // Storage unavailable — the key simply won't survive a reload.
  }
  notify();
}

export function clearOperatorKey(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // nothing to clear
  }
  notify();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * The current operator key, or "" when locked.
 *
 * `useSyncExternalStore`'s third argument is load-bearing, not ceremony: it is the
 * server snapshot. Without it the server would render "locked" and the first client
 * render would read sessionStorage and render "unlocked" — a hydration mismatch. React
 * renders the server snapshot during hydration and only then re-renders with the real
 * value. `getOperatorKey` returns a string rather than a fresh object, which satisfies
 * the snapshot-stability requirement.
 *
 * The subscription also lets `api.ts` flip every mounted gate back to locked when a
 * request comes back 403, with no context provider and no prop drilling.
 */
export function useOperatorKey(): string {
  return useSyncExternalStore(subscribe, getOperatorKey, () => "");
}
