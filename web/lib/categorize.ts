// Merchant-at-a-time categorizing (home "N עסקאות לסיווג" sheet).
import type { Category, Group, Uncategorized } from "./api";

/** Transactions behind the uncategorized merchants. */
export const pendingCount = (list: Pick<Uncategorized, "count">[]) => list.reduce((n, u) => n + u.count, 0);

/** Groups a merchant may be sorted into from the quick buttons (spending first; credits also income). */
export const quickGroups = (total: number): Group[] => (total > 0 ? ["income", "variable", "fixed", "savings"] : ["variable", "fixed", "savings"]);

/** Up to `n` quick-pick categories: most used first (usage = ids by use), then by sort order; only `groups`. */
export function quickPicks(cats: Category[], usage: number[], groups: Group[], n = 6): Category[] {
  const rank = new Map(usage.map((id, i) => [id, i]));
  return cats
    .filter((c) => groups.includes(c.group))
    .sort((a, b) => (rank.get(a.id) ?? Infinity) - (rank.get(b.id) ?? Infinity) || a.sort_order - b.sort_order || a.id - b.id)
    .slice(0, n);
}
