/** Download link for the CSV export of the transactions matching `params` (same filters as the list, no paging). */
export function exportHref(params: URLSearchParams | string) {
  const p = new URLSearchParams(params);
  p.delete("limit");
  p.delete("cursor");
  const qs = p.toString();
  return `/api/transactions/export.csv${qs ? `?${qs}` : ""}`;
}
