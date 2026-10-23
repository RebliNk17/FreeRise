// Temporary home view filter ("חשבונות להצגה"): account ids hidden in this browser only.
// Sent to the API as ?hide_accounts=1,2. Hidden (not shown) ids are stored so a newly synced
// account shows up by default. Different from the permanent "exclude from cash flow".
import { useSyncExternalStore } from "react";

const KEY = "freerise-hidden-accounts";
const CHANGED = "freerise:hidden-accounts";

export function parseHidden(raw: string | null): number[] {
  try {
    const v = JSON.parse(raw ?? "[]");
    return Array.isArray(v) ? v.filter((x): x is number => Number.isInteger(x)) : [];
  } catch {
    return [];
  }
}

function read(): string {
  try {
    return localStorage.getItem(KEY) ?? "[]";
  } catch {
    return "[]";
  }
}

export function setHidden(ids: number[]) {
  try {
    if (ids.length) localStorage.setItem(KEY, JSON.stringify([...new Set(ids)].sort((a, b) => a - b)));
    else localStorage.removeItem(KEY);
  } catch {}
  window.dispatchEvent(new Event(CHANGED));
}

const subscribe = (cb: () => void) => {
  window.addEventListener(CHANGED, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(CHANGED, cb);
    window.removeEventListener("storage", cb);
  };
};

/** Hidden account ids (raw JSON is the snapshot so it stays referentially stable). */
export function useHiddenAccounts(): number[] {
  return parseHidden(useSyncExternalStore(subscribe, read, () => "[]"));
}

/** Append ?hide_accounts=… when something is hidden. */
export const withHidden = (path: string, ids: number[]) => (ids.length ? `${path}${path.includes("?") ? "&" : "?"}hide_accounts=${ids.join(",")}` : path);

/** Quick "רק של <holder>" choices: per holder, the ids to hide to show only theirs. Empty for one holder. */
export function holderChoices(accounts: { id: number; holder: string }[]): { holder: string; hide: number[] }[] {
  const holders = [...new Set(accounts.map((a) => a.holder).filter(Boolean))];
  if (holders.length < 2) return [];
  return holders.map((h) => ({ holder: h, hide: accounts.filter((a) => a.holder !== h).map((a) => a.id) }));
}
