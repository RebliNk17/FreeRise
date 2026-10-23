"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Check, Download, Search, TriangleAlert, X } from "lucide-react";
import { exportHref } from "@/lib/exportCsv";
import { Amount } from "@/components/Amount";
import { CategoryPicker } from "@/components/CategoryPicker";
import { Switch } from "@/components/Switch";
import { api, type Page, type Transaction } from "@/lib/api";
import { categoryLabel, formatDate } from "@/lib/format";
import { EmptyState } from "@/components/Card";

const WEEKDAY = new Intl.DateTimeFormat("he-IL", { weekday: "long" });

// Drill-down filters from cash flow / reconcile (?category_id|uncategorized|account_id, from, to; label is display-only).
// ?q and ?include_excluded only seed the search box and switch.
const FILTER_KEYS = ["category_id", "uncategorized", "account_id", "from", "to"];

function exportParams(filters: string, q: string, includeExcluded: boolean) {
  const p = new URLSearchParams(filters);
  if (q) p.set("q", q);
  if (includeExcluded) p.set("include_excluded", "true");
  return p;
}

function query(filters: string, q: string, includeExcluded: boolean, cursor?: string) {
  const p = new URLSearchParams(filters);
  p.set("limit", "100");
  if (q) p.set("q", q);
  if (includeExcluded) p.set("include_excluded", "true");
  if (cursor) p.set("cursor", cursor);
  return api<Page<Transaction>>(`/transactions?${p}`);
}

export default function TransactionsPage() {
  return (
    <Suspense>
      <Transactions />
    </Suspense>
  );
}

function Transactions() {
  const sp = useSearchParams();
  const filters = new URLSearchParams([...sp].filter(([k]) => FILTER_KEYS.includes(k))).toString();
  const [picking, setPicking] = useState<Transaction | null>(null);
  const [q, setQ] = useState(sp.get("q") ?? "");
  const [includeExcluded, setIncludeExcluded] = useState(sp.get("include_excluded") === "true");
  const [items, setItems] = useState<Transaction[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState(false);
  // Bumped on every filter change; responses from an older generation are dropped.
  const gen = useRef(0);

  useEffect(() => {
    const g = ++gen.current;
    const t = setTimeout(() => {
      query(filters, q.trim(), includeExcluded)
        .then((page) => {
          if (g !== gen.current) return;
          setItems(page.items);
          setCursor(page.next_cursor);
          setError(false);
        })
        .catch(() => g === gen.current && setError(true));
    }, 250);
    return () => clearTimeout(t);
  }, [filters, q, includeExcluded]);

  async function loadMore() {
    if (!cursor) return;
    const g = gen.current;
    try {
      const page = await query(filters, q.trim(), includeExcluded, cursor);
      if (g !== gen.current) return;
      setItems((prev) => [...(prev ?? []), ...page.items]);
      setCursor(page.next_cursor);
      setError(false);
    } catch {
      if (g === gen.current) setError(true);
    }
  }

  const days = new Map<string, Transaction[]>();
  const manyHolders = new Set((items ?? []).map((t) => t.account_holder)).size > 1;
  for (const t of items ?? []) days.set(t.date, [...(days.get(t.date) ?? []), t]);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="page-title">עסקאות</h1>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search size={18} className="pointer-events-none absolute top-1/2 right-3.5 -translate-y-1/2 text-faint" />
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="חיפוש עסקה"
            className="input pr-10"
            aria-label="חיפוש עסקה"
          />
        </div>
        <Switch checked={includeExcluded} onChange={setIncludeExcluded} label="הצגת חשבונות מוחרגים" />
        <a className="btn-secondary" href={exportHref(exportParams(filters, q.trim(), includeExcluded))} download>
          <Download size={16} aria-hidden /> ייצוא לאקסל
        </a>
      </div>

      {filters && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <span className="flex-1">
            מסונן
            {sp.get("label") && ` · ${sp.get("label")}`}
            {sp.get("from") && (
              <>
                {" · "}
                <span dir="ltr">
                  {formatDate(sp.get("from")!)}–{sp.get("to") ? formatDate(sp.get("to")!) : ""}
                </span>
              </>
            )}
          </span>
          <Link href="/transactions" className="btn-ghost" aria-label="ניקוי סינון">
            <X size={14} /> ניקוי
          </Link>
        </p>
      )}
      {error && <p className="rounded-2xl bg-danger-soft px-4 py-3 text-sm font-semibold text-danger-strong" role="alert">טעינת העסקאות נכשלה.</p>}
      {items === null && !error && <p className="text-muted">טוען…</p>}
      {items?.length === 0 && <EmptyState text="אין עסקאות להצגה." />}

      {[...days].map(([day, txns]) => (
        <section key={day} className="flex flex-col gap-1.5">
          <h2 className="px-1 font-sans text-[13px] font-semibold text-muted">
            {WEEKDAY.format(new Date(`${day}T12:00:00`))} · <span dir="ltr">{formatDate(day)}</span>
          </h2>
          <ul className="card divide-y divide-hairline">
            {txns.map((t) => (
              <li key={t.id} className="flex items-center gap-3 px-3.5 py-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-bold">{t.description}</span>
                    {t.installment_total ? (
                      <span dir="ltr" className="shrink-0 rounded-full bg-sun-soft px-2 text-[11px] font-semibold">
                        {t.installment_number}/{t.installment_total}
                      </span>
                    ) : null}
                    {t.status === "pending" && <span className="shrink-0 text-xs text-muted">בהמתנה</span>}
                    {t.reconcile_status && (
                      <span className={`flex size-6 shrink-0 items-center justify-center rounded-full ${t.reconcile_status === "matched" ? "bg-brand-soft text-brand" : "bg-danger-soft text-danger"}`} aria-label={t.reconcile_status === "matched" ? "תואם לחיובי הכרטיס" : "לא תואם לחיובי הכרטיס"}>
                        {t.reconcile_status === "matched" ? <Check size={13} aria-hidden /> : <TriangleAlert size={13} aria-hidden />}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted">
                    <span className="truncate">
                      {t.account_name}
                      {manyHolders && t.account_holder && ` (${t.account_holder})`}
                    </span>
                    {t.cycle_shift && t.cycle_label && <span className="shrink-0 rounded-full bg-brand-soft px-2 text-[10px] font-semibold text-brand">שויך ל{t.cycle_label.split(" ")[0]}</span>}
                    <button
                      onClick={() => setPicking(t)}
                      className={`relative shrink-0 rounded-full px-2.5 py-0.5 font-semibold after:absolute after:-inset-y-2.5 after:inset-x-0 ${t.category_id ? "bg-sunken text-text" : "border border-dashed border-sun-strong text-muted"}`}
                      aria-label={`שינוי קטגוריה: ${categoryLabel(t.category_name)}`}
                    >
                      {categoryLabel(t.category_name)}
                    </button>
                  </div>
                </div>
                <Amount value={t.amount} className="shrink-0 font-bold" />
              </li>
            ))}
          </ul>
        </section>
      ))}

      {picking && (
        <CategoryPicker
          txn={picking}
          onClose={() => setPicking(null)}
          onSaved={(category_id, category_name, applyToPast) => {
            const same = (x: Transaction) => x.id === picking.id || (applyToPast && !!picking.merchant_key && x.merchant_key === picking.merchant_key);
            setItems((prev) => prev?.map((x) => (same(x) ? { ...x, category_id, category_name, category_source: "manual" } : x)) ?? null);
            setPicking(null);
          }}
        />
      )}

      {cursor && (
        <button onClick={loadMore} className="btn-ghost self-center">
          טעינת עוד
        </button>
      )}
    </div>
  );
}
