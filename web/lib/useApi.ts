"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/** GET `path` on mount / path change. data: undefined = loading (cleared when path changes).
 * Changing `refresh` refetches in the background (data kept until the new response lands). */
export function useApi<T>(path: string, refresh?: unknown) {
  const [state, setState] = useState<{ path: string; data?: T; error: boolean }>({ path, error: false });
  // Bumped per request; only the latest response may land.
  const gen = useRef(0);
  const reload = useCallback(() => {
    const g = ++gen.current;
    return api<T>(path)
      .then((data) => g === gen.current && setState({ path, data, error: false }))
      .catch(() => g === gen.current && setState({ path, error: true }));
  }, [path]);
  useEffect(() => {
    reload();
  }, [reload, refresh]);
  const current = state.path === path; // stale path → behave as loading
  const setData = useCallback(
    (fn: (d: T | undefined) => T | undefined) => setState((s) => (s.path === path ? { ...s, data: fn(s.data) } : s)),
    [path],
  );
  return { data: current ? state.data : undefined, setData, error: current && state.error, reload };
}
