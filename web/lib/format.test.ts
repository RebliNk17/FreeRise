import { expect, test } from "bun:test";
import { categoryLabel, formatCycleRange, formatCycleLabel, formatDate, formatILS, formatPct, formatPercentValue, txnCount, weekBarPercent } from "./format";

test("formatILS negative non-integer", () => {
  const s = formatILS(-120.5);
  expect(s).toContain("120.50");
  expect(s).toContain("₪");
});

test("formatILS integer has thousands separator and no decimals", () => {
  const s = formatILS(1000);
  expect(s).toContain("1,000");
  expect(s).not.toContain(".00");
});

test("formatDate date-only and datetime", () => {
  expect(formatDate("2026-10-03")).toBe("03.10.26");
  expect(formatDate("2026-01-31T12:00:00")).toBe("31.01.26");
});


test("formatCycleLabel uses start month, crosses year", () => {
  expect(formatCycleLabel("2026-09-10", "2026-10-09")).toBe("ספטמבר 2026 (10.9 עד 9.10)");
  expect(formatCycleLabel("2026-12-10", "2027-01-09")).toBe("דצמבר 2026 (10.12 עד 9.1)");
});

test("weekBarPercent clamps and handles zero allowance", () => {
  expect(weekBarPercent(50, 200)).toBe(25);
  expect(weekBarPercent(300, 200)).toBe(100);
  expect(weekBarPercent(-20, 200)).toBe(0);
  expect(weekBarPercent(10, 0)).toBe(100);
  expect(weekBarPercent(0, 0)).toBe(0);
});

test("formatPct and categoryLabel", () => {
  expect(formatPct(0.1064)).toBe("10.64%");
  expect(formatPct(-0.005)).toBe("-0.50%");
  expect(formatPct(null)).toBe("—");
  expect(formatPercentValue(0.6)).toBe("0.60%");
  expect(formatPercentValue(null)).toBe("—");
  expect(categoryLabel("כלכלה")).toBe("סופר");
  expect(categoryLabel(null)).toBe("לא מסווג");
});

test("txnCount uses the singular for one", () => {
  expect(txnCount(1)).toBe("עסקה אחת");
  expect(txnCount(0)).toBe("0 עסקאות");
  expect(txnCount(3)).toBe("3 עסקאות");
});

test("formatCycleRange", () => {
  expect(formatCycleRange("2026-10-10", "2026-11-09")).toBe("10.10 – 9.11");
});
