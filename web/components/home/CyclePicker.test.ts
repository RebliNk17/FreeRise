import { expect, test } from "bun:test";
import { cycleList } from "./CyclePicker";

test("cycleList starts at the cycle containing today and clamps short months", () => {
  const l = cycleList(10, new Date(2026, 9, 24), 3);
  expect(l.map((c) => [c.label, c.href])).toEqual([
    ["אוקטובר 2026 (10.10 עד 9.11)", "/home"],
    ["ספטמבר 2026 (10.9 עד 9.10)", "/home/2026/9"],
    ["אוגוסט 2026 (10.8 עד 9.9)", "/home/2026/8"],
  ]);
  expect(cycleList(10, new Date(2026, 9, 5), 1)[0].label).toStartWith("ספטמבר 2026");
  expect(cycleList(31, new Date(2026, 2, 1), 2).map((c) => c.label)).toEqual(["פברואר 2026 (28.2 עד 30.3)", "ינואר 2026 (31.1 עד 27.2)"]);
});
