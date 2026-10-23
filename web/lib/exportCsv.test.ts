import { expect, test } from "bun:test";
import { exportHref } from "./exportCsv";

test("exportHref keeps filters, drops paging", () => {
  expect(exportHref("")).toBe("/api/transactions/export.csv");
  expect(exportHref("category_id=3&limit=100&cursor=abc&q=%D7%A1")).toBe("/api/transactions/export.csv?category_id=3&q=%D7%A1");
});
