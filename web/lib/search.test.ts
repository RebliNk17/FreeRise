import { expect, test } from "bun:test";
import type { Transaction } from "./api";
import { filterParams, parseFilters, searchHref, toTxn } from "./search";

test("filters round-trip through the query string", () => {
  const f = parseFilters(new URLSearchParams("q=%D7%A1%D7%95%D7%A4%D7%A8&from=2026-09-01&category_id=7&junk=1"));
  expect(f).toEqual({ q: "סופר", from: "2026-09-01", to: "", category_id: 7 });
  expect(filterParams(f).toString()).toBe("q=%D7%A1%D7%95%D7%A4%D7%A8&from=2026-09-01&category_id=7");
  expect(parseFilters(new URLSearchParams("category_id=x")).category_id).toBeNull();
});

test("searchHref", () => {
  expect(searchHref({})).toBe("/search");
  expect(searchHref({ category_id: 3, from: "2026-01-01" })).toBe("/search?from=2026-01-01&category_id=3");
});

test("toTxn maps a list row for the sheet", () => {
  const row = {
    id: 1, account_id: 2, account_name: "מקס ••1234", account_holder: "שי", cycle_shift: null, cycle_label: null, fixed_income_id: null, cycle_date_source: null,
    date: "2026-09-01", processed_date: "2026-09-02", amount: "-300", original_amount: null, original_currency: null, description: "שופרסל", memo: null,
    installment_number: null, installment_total: null, status: "completed", category_id: 5, category_name: "כלכלה", category_source: "rule", merchant_key: "שופרסל",
    group: "variable", note: null, review: null, split: [{ category_id: 5, category_name: "כלכלה", amount: -300 }],
  } as Transaction;
  const t = toTxn(row);
  expect([t.amount, t.account_label, t.group, t.split_total]).toEqual([-300, "מקס ••1234", "variable", -300]);
});
