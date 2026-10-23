import { expect, test } from "bun:test";
import { historyPath, progressHistoryPath } from "./history";

test("historyPath", () => {
  expect(historyPath("fixed", { label_year: 2026, label_month: 10 }, [])).toBe("/home/history?kind=fixed&year=2026&month=10");
  expect(historyPath("category", { label_year: 2026, label_month: 9 }, [4], 7)).toBe("/home/history?kind=category&year=2026&month=9&category_id=7&hide_accounts=4");
});

test("progressHistoryPath", () => {
  expect(progressHistoryPath("variable", 12, null)).toBe("/progress/history?group=variable&months=12");
  expect(progressHistoryPath("income", 3, 5)).toBe("/progress/history?group=income&months=3&category_id=5");
});
