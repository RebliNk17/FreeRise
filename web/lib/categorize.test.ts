import { expect, test } from "bun:test";
import type { Category } from "./api";
import { pendingCount, quickGroups, quickPicks } from "./categorize";

const cat = (id: number, group: Category["group"], sort_order = 0): Category => ({ id, name: `c${id}`, group, sort_order });

test("pendingCount sums merchant counts", () => {
  expect(pendingCount([{ count: 2 }, { count: 3 }])).toBe(5);
  expect(pendingCount([])).toBe(0);
});

test("quickPicks: most used first, then sort order, filtered by group", () => {
  const cats = [cat(1, "variable", 2), cat(2, "variable", 1), cat(3, "fixed", 0), cat(4, "transfer"), cat(5, "variable", 0)];
  expect(quickPicks(cats, [3, 1], ["variable", "fixed"]).map((c) => c.id)).toEqual([3, 1, 5, 2]);
  expect(quickPicks(cats, [4], ["variable"], 2).map((c) => c.id)).toEqual([5, 2]);
});

test("quickGroups offers income only for credits", () => {
  expect(quickGroups(100)).toContain("income");
  expect(quickGroups(-100)).not.toContain("income");
});
