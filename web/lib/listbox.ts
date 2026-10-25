/** Pure helpers behind components/ui/Select.tsx (listbox keyboard model). */
import type { ReactNode } from "react";

/** `keywords`: extra text the search matches, e.g. English names of a Hebrew label. */
export type Option = { value: string; label: string; keywords?: string; icon?: ReactNode; group?: string; disabled?: boolean };

/** Next enabled index for a navigation key, or `current` when the key isn't one / nothing is enabled. */
export function moveIndex(options: Option[], current: number, key: string): number {
  const enabled = options.flatMap((o, i) => (o.disabled ? [] : [i]));
  if (!enabled.length) return -1;
  if (key === "Home") return enabled[0];
  if (key === "End") return enabled.at(-1)!;
  if (key === "ArrowDown") return enabled.find((i) => i > current) ?? enabled[0];
  if (key === "ArrowUp") return enabled.findLast((i) => i < current) ?? enabled.at(-1)!;
  return current;
}

/** Type-ahead: first enabled option after `from` whose label starts with `query` (wrapping); -1 if none. */
export function typeahead(options: Option[], query: string, from: number): number {
  const q = query.toLocaleLowerCase();
  if (!q) return -1;
  // One letter (or the same letter repeated) cycles through options with that initial.
  const same = [...q].every((c) => c === q[0]);
  const start = same ? from + 1 : from;
  const needle = same ? q[0] : q;
  for (let k = 0; k < options.length; k++) {
    const i = (Math.max(start, 0) + k) % options.length;
    if (!options[i].disabled && options[i].label.toLocaleLowerCase().startsWith(needle)) return i;
  }
  return -1;
}

/** Options whose label or keywords contain every whitespace-separated term of `q` (case-insensitive). */
export function filterOptions(options: Option[], q: string): Option[] {
  const terms = q.toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const text = (o: Option) => `${o.label} ${o.keywords ?? ""}`.toLocaleLowerCase();
  return terms.length ? options.filter((o) => terms.every((t) => text(o).includes(t))) : options;
}
