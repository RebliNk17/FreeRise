// Search over all transactions (/search): query string <-> filters, API rows -> the sheet's Txn.
import type { Transaction } from "./api";
import type { Txn } from "./home";

export type SearchFilters = { q: string; from: string; to: string; category_id: number | null };
export const EMPTY_FILTERS: SearchFilters = { q: "", from: "", to: "", category_id: null };

/** Filters from a URL query (/search?q=…&from=…&to=…&category_id=…). */
export function parseFilters(sp: URLSearchParams): SearchFilters {
  const cid = Number(sp.get("category_id"));
  return { q: sp.get("q") ?? "", from: sp.get("from") ?? "", to: sp.get("to") ?? "", category_id: Number.isInteger(cid) && cid > 0 ? cid : null };
}

/** API query for the filters (empty ones left out). */
export function filterParams(f: SearchFilters): URLSearchParams {
  const p = new URLSearchParams();
  if (f.q.trim()) p.set("q", f.q.trim());
  if (f.from) p.set("from", f.from);
  if (f.to) p.set("to", f.to);
  if (f.category_id != null) p.set("category_id", String(f.category_id));
  return p;
}

/** Open the search prefilled, e.g. from a category or the cost screen. */
export const searchHref = (f: Partial<SearchFilters>) => {
  const qs = filterParams({ ...EMPTY_FILTERS, ...f }).toString();
  return `/search${qs ? `?${qs}` : ""}`;
};

/** A list row as the transaction sheet's Txn (the sheet is shared with home). */
export const toTxn = (t: Transaction): Txn => ({
  id: t.id,
  date: t.date,
  amount: Number(t.amount),
  description: t.description,
  merchant_key: t.merchant_key,
  category_id: t.category_id,
  category_name: t.category_name,
  group: t.group ?? null,
  account_id: t.account_id,
  account_label: t.account_name,
  note: t.note ?? null,
  installment_number: t.installment_number,
  installment_total: t.installment_total,
  status: t.status,
  account_holder: t.account_holder,
  cycle_shift: t.cycle_shift,
  cycle_label: t.cycle_label,
  fixed_income_id: t.fixed_income_id,
  cycle_date_source: t.cycle_date_source,
  split_total: t.split ? Number(t.amount) : null,
  split: t.split ?? null,
  review: t.review ?? null,
});
