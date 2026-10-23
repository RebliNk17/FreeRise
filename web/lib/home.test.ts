import { expect, test } from "bun:test";
import { homeFixture } from "./fixtures/home";
import { accountWithHolder, daysLabel, findTxn, fixedStatusLabel, isIdle, leftLabel, mapTxns, splitMoney, weekDays, weekOver, shiftChip, weekStatus, wrapIndex, totalSegments } from "./home";

test("splitMoney splits integer and decimal parts", () => {
  expect(splitMoney(1819.2)).toEqual({ sign: "", int: "1,819", dec: ".2" });
  expect(splitMoney(1000)).toEqual({ sign: "", int: "1,000", dec: "" });
  expect(splitMoney(-12.345)).toEqual({ sign: "-", int: "12", dec: ".35" });
  expect(splitMoney(-0.001)).toEqual({ sign: "", int: "0", dec: "" });
});

test("weekStatus", () => {
  const [past, current] = homeFixture.variable.weeks;
  expect(weekStatus(past)).toBe("past");
  expect(weekStatus(current)).toBe("current");
  expect(weekStatus({ is_current: false, is_past: false })).toBe("future");
});

test("wrapIndex wraps both ways", () => {
  expect(wrapIndex(3, 3)).toBe(0);
  expect(wrapIndex(-1, 3)).toBe(2);
  expect(wrapIndex(-4, 3)).toBe(2);
  expect(wrapIndex(5, 0)).toBe(0);
});

test("fixed status labels incl. overdue", () => {
  expect(fixedStatusLabel("overdue")).toBe("לא ירד עדיין");
  expect(fixedStatusLabel("charged")).toBe("ירד");
  expect(fixedStatusLabel("expected")).toBe("צפוי");
});

test("leftLabel over and under", () => {
  expect(leftLabel(100, 300)).toEqual({ text: "נשאר להוציא", value: 200, over: false });
  expect(leftLabel(350, 300)).toEqual({ text: "חריגה של", value: 50, over: true });
});

test("mapTxns updates every copy and can drop", () => {
  const noted = mapTxns(homeFixture, (t) => (t.id === 1 ? { ...t, note: "x" } : t));
  expect(noted.variable.weeks[0].transactions[0].note).toBe("x");
  expect(noted.tracked[0].weeks![0].transactions[0].note).toBe("x");
  expect(findTxn(noted, 1)?.note).toBe("x");
  expect(homeFixture.tracked[0].transactions[0].note).toBeNull();
  const dropped = mapTxns(homeFixture, (t) => (t.id === 3 ? null : t));
  expect(dropped.fixed.groups[0].items[0].transactions).toHaveLength(0);
  expect(findTxn(dropped, 3)).toBeUndefined();
});

test("weekOver: negative left or spent above expected", () => {
  expect(weekOver({ spent: 100, left: 50, expected: 150 })).toBe(false);
  expect(weekOver({ spent: 100, left: -1, expected: null })).toBe(true);
  expect(weekOver({ spent: 800, left: 0, expected: 400 })).toBe(true); // past week, left pinned to 0
  expect(weekOver({ spent: 400, left: 0, expected: 400 })).toBe(false);
});

test("isIdle only for 0 spent and 0 expected", () => {
  expect(isIdle({ spent: 0, expected: 0 })).toBe(true);
  expect(isIdle({ spent: 0, expected: 10 })).toBe(false);
  expect(isIdle({ spent: 5, expected: 0 })).toBe(false);
});

test("weekDays / daysLabel", () => {
  expect(weekDays({ start: "2026-10-10", end: "2026-10-10" })).toBe(1);
  expect(weekDays({ start: "2026-10-25", end: "2026-10-31" })).toBe(7);
  expect(weekDays({ start: "2026-10-31", end: "2026-11-01" })).toBe(2);
  expect(daysLabel(1)).toBe("יום אחד");
  expect(daysLabel(4)).toBe("4 ימים");
});

test("account holder suffix and cycle shift chip", () => {
  expect(accountWithHolder({ account_label: "ישראכרט ••5678", account_holder: "שי" }, true)).toBe("ישראכרט ••5678 (שי)");
  expect(accountWithHolder({ account_label: "ישראכרט ••5678", account_holder: "שי" }, false)).toBe("ישראכרט ••5678");
  expect(accountWithHolder({ account_label: "ישראכרט ••5678", account_holder: "" }, true)).toBe("ישראכרט ••5678");
  expect(shiftChip({ cycle_shift: "previous", cycle_label: "ספטמבר 2026" })).toBe("שויך לספטמבר");
  expect(shiftChip({ cycle_shift: null, cycle_label: null })).toBeNull();
});


test("totalSegments: shares of the bigger of spent/expected", () => {
  const d = { fixed: { spent: 300, expected: 400, groups: [] }, variable: { spent: 500, allowance: 500, weeks: [] }, savings: { spent: 200, expected: 100, transactions: [] }, total: { spent: 1000, expected: 1000 } };
  const s = totalSegments(d);
  expect(s.map((x) => [x.key, x.percent, x.expected])).toEqual([
    ["fixed", 30, 400],
    ["variable", 50, 500],
    ["savings", 20, 100],
  ]);
  const over = totalSegments({ ...d, total: { spent: 2000, expected: 1000 } });
  expect(over[1].percent).toBe(25);
});
