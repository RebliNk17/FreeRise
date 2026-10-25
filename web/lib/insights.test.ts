import { expect, test } from "bun:test";
import { advanceDelay, BAND, ctaLabel, illustrationFor, INTRO_MS, splitAmounts } from "./insights";

const bold = (s: string) => splitAmounts(s).filter((p) => p.bold).map((p) => p.text);

test("splitAmounts bolds ₪ amounts on either side, not trailing punctuation", () => {
  expect(splitAmounts("יחסרו בערך ₪1,200. האטה")).toEqual([
    { text: "יחסרו בערך ", bold: false },
    { text: "₪1,200", bold: true },
    { text: ". האטה", bold: false },
  ]);
  expect(bold("הוצאתם 350.5 ₪ על עמלות ו-₪12")).toEqual(["350.5 ₪", "₪12"]);
  expect(bold("ירידה של ₪40, יפה")).toEqual(["₪40"]);
  expect(bold("אין סכומים כאן, רק 30%")).toEqual([]);
  expect(splitAmounts("₪5")).toEqual([{ text: "₪5", bold: true }]);
  expect(splitAmounts("")).toEqual([]);
});

test("illustrationFor maps kinds", () => {
  expect(illustrationFor("category_up", "warning")).toBe("spike");
  expect(illustrationFor("category_creep", "warning")).toBe("spike");
  expect(illustrationFor("category_trend", "warning")).toBe("spike");
  expect(illustrationFor("category_trend", "positive")).toBe("shrink");
  expect(illustrationFor("category_down", "positive")).toBe("shrink");
  expect(illustrationFor("negative_cycle", "warning")).toBe("drain");
  expect(illustrationFor("low_balance_before_income", "warning")).toBe("drain");
  expect(illustrationFor("idle_cash", "positive")).toBe("piggy");
  expect(illustrationFor("saving_capacity", "positive")).toBe("piggy");
  expect(illustrationFor("fees", "warning")).toBe("receipt");
  expect(illustrationFor("unknown_card", "warning")).toBe("card");
  expect(illustrationFor("no_goal", "info")).toBe("sunrise");
  expect(illustrationFor("goal_status", "info")).toBe("sunrise");
  expect(illustrationFor("whatever_new", "info")).toBe("coin");
});

test("severity → band theme, CTA defaults", () => {
  expect(BAND).toEqual({ warning: "bg-band-warning", positive: "bg-band-positive", info: "bg-band-info" });
  const it = { kind: "fees", severity: "warning" as const, action_label: null, link: "/x" };
  expect(ctaLabel(it)).toBe("לפירוט העמלות");
  expect(ctaLabel({ ...it, action_label: "קדימה" })).toBe("קדימה");
  expect(ctaLabel({ ...it, link: null })).toBeNull();
});

test("advanceDelay: 12s after the intro; off when paused, reduced, hidden or after interaction", () => {
  const base = { n: 3, reduced: false, hover: false, focus: false, hidden: false, interacted: false, dragging: false };
  expect(advanceDelay(base)).toBe(INTRO_MS + 12_000);
  for (const k of ["reduced", "hover", "focus", "hidden", "interacted", "dragging"] as const) expect(advanceDelay({ ...base, [k]: true })).toBeNull();
  expect(advanceDelay({ ...base, n: 1 })).toBeNull();
});
