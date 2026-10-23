"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, Download, Search, SlidersHorizontal, StickyNote, X } from "lucide-react";
import { Amount } from "@/components/Amount";
import { EmptyState } from "@/components/Card";
import { CategorySelect } from "@/components/CategorySelect";
import { HomeContext, type HomeCtx } from "@/components/home/context";
import { TxnSheet } from "@/components/home/TxnSheet";
import { api, type Page, type Transaction } from "@/lib/api";
import { exportHref } from "@/lib/exportCsv";
import { categoryLabel, formatDate } from "@/lib/format";
import type { HomeData, Txn } from "@/lib/home";
import { filterParams, parseFilters, toTxn, type SearchFilters } from "@/lib/search";

const WEEKDAY = new Intl.DateTimeFormat("he-IL", { weekday: "long" });
const PAGE = 50;
// The transaction sheet is shared with home; here it only needs "nothing moved to next cycle".
const NO_HOME = { moved_next: { transactions: [] } } as unknown as HomeData;

function fetchPage(f: SearchFilters, cursor?: string) {
  const p = filterParams(f);
  p.set("limit", String(PAGE));
  if (cursor) p.set("cursor", cursor);
  return api<Page<Transaction>>(`/transactions?${p}`);
}

export default function SearchPage() {
  return (
    <Suspense>
      <SearchScreen />
    </Suspense>
  );
}

/** Search all transactions: one box (merchant, card digits/name/holder, amount "120" or "100-200"),
 * date range and category; paginated; a row opens the transaction sheet; CSV export of the results. */
function SearchScreen() {
  const router = useRouter();
  const sp = useSearchParams();
  const [f, setF] = useState<SearchFilters>(() => parseFilters(sp));
  const [showFilters, setShowFilters] = useState(!!(f.from || f.to || f.category_id));
  const [items, setItems] = useState<Transaction[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [sheet, setSheet] = useState<Txn | null>(null);
  const [version, setVersion] = useState(0);
  const gen = useRef(0); // only the latest request may land
  const key = filterParams(f).toString();

  useEffect(() => {
    const g = ++gen.current;
    const t = setTimeout(() => {
      fetchPage(f)
        .then((page) => {
          if (g !== gen.current) return;
          setItems(page.items);
          setCursor(page.next_cursor);
          setError(false);
        })
        .catch(() => g === gen.current && setError(true));
      router.replace(`/search${key ? `?${key}` : ""}`, { scroll: false });
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- key covers f
  }, [key, version]);

  async function loadMore() {
    if (!cursor) return;
    const g = gen.current;
    try {
      const page = await fetchPage(f, cursor);
      if (g !== gen.current) return;
      setItems((prev) => [...(prev ?? []), ...page.items]);
      setCursor(page.next_cursor);
    } catch {
      if (g === gen.current) setError(true);
    }
  }

  const ctx: HomeCtx = {
    data: NO_HOME,
    mutate: async (_optimistic, request) => {
      try {
        await request();
        return true;
      } catch {
        setError(true);
        return false;
      } finally {
        setVersion((v) => v + 1);
      }
    },
    openTxn: setSheet,
    version,
  };

  const days = new Map<string, Transaction[]>();
  for (const t of items ?? []) days.set(t.date, [...(days.get(t.date) ?? []), t]);
  const manyHolders = new Set((items ?? []).map((t) => t.account_holder)).size > 1;
  const filtered = !!(f.from || f.to || f.category_id);

  return (
    <HomeContext value={ctx}>
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <button type="button" className="icon-btn size-11" aria-label="חזרה" onClick={() => router.back()}>
            <ArrowRight size={18} />
          </button>
          <div className="relative flex-1">
            <Search size={18} className="pointer-events-none absolute top-1/2 right-3.5 -translate-y-1/2 text-faint" aria-hidden />
            <input
              type="search"
              value={f.q}
              onChange={(e) => setF({ ...f, q: e.target.value })}
              placeholder="בית עסק, 4 ספרות כרטיס או סכום"
              className="input pr-10"
              aria-label="חיפוש עסקאות"
              autoFocus
            />
          </div>
          <button type="button" className={`icon-btn size-11 ${filtered ? "bg-brand-soft text-brand" : ""}`} aria-label="סינון" aria-expanded={showFilters} onClick={() => setShowFilters((s) => !s)}>
            <SlidersHorizontal size={18} />
          </button>
        </div>
        <p className="px-1 text-xs text-muted">סכום: &quot;120&quot; מוצא גם 119.90–120.10, &quot;100-200&quot; טווח.</p>

        {showFilters && (
          <div className="card flex flex-col gap-3 p-3.5">
            <div className="grid grid-cols-2 gap-2">
              <label className="flex flex-col gap-1 text-xs text-muted">
                מתאריך
                <input type="date" className="input" dir="ltr" value={f.from} onChange={(e) => setF({ ...f, from: e.target.value })} />
              </label>
              <label className="flex flex-col gap-1 text-xs text-muted">
                עד תאריך
                <input type="date" className="input" dir="ltr" value={f.to} onChange={(e) => setF({ ...f, to: e.target.value })} />
              </label>
            </div>
            <CategorySelect value={f.category_id} onChange={(id) => setF({ ...f, category_id: id })} label="קטגוריה" />
            {filtered && (
              <button type="button" className="btn-ghost self-start" onClick={() => setF({ ...f, from: "", to: "", category_id: null })}>
                <X size={14} aria-hidden /> ניקוי סינון
              </button>
            )}
          </div>
        )}

        <div className="flex items-center justify-between gap-2">
          <p className="text-sm text-muted" aria-live="polite">
            {items == null ? "" : items.length === 0 ? "" : `${items.length}${cursor ? "+" : ""} תוצאות`}
          </p>
          <a className="btn-secondary" href={exportHref(filterParams(f))} download>
            <Download size={16} aria-hidden /> ייצוא לאקסל
          </a>
        </div>

        {error && (
          <p className="rounded-2xl bg-danger-soft px-4 py-3 text-sm font-semibold text-danger-strong" role="alert">
            הטעינה נכשלה.
          </p>
        )}
        {items === null && !error && <p className="text-muted">טוען…</p>}
        {items?.length === 0 && <EmptyState text="לא נמצאו עסקאות." />}

        {[...days].map(([day, txns]) => (
          <section key={day} className="flex flex-col gap-1.5">
            <h2 className="px-1 font-sans text-[13px] font-semibold text-muted">
              {WEEKDAY.format(new Date(`${day}T12:00:00`))} · <span dir="ltr">{formatDate(day)}</span>
            </h2>
            <ul className="card divide-y divide-hairline">
              {txns.map((t) => (
                <li key={t.id}>
                  <button type="button" className="flex min-h-14 w-full items-center gap-3 px-3.5 py-3 text-start hover:bg-sunken/50" onClick={() => setSheet(toTxn(t))}>
                    <span className="block min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <span className="truncate font-bold">{t.description}</span>
                        {t.installment_total ? (
                          <span dir="ltr" className="shrink-0 rounded-full bg-sun-soft px-2 text-[11px] font-semibold">
                            {t.installment_number}/{t.installment_total}
                          </span>
                        ) : null}
                        {t.note && <StickyNote size={14} className="shrink-0 text-muted" aria-label="יש הערה" />}
                        {t.status === "pending" && <span className="shrink-0 text-xs text-muted">בקליטה</span>}
                      </span>
                      <span className="block truncate text-xs text-muted">
                        {t.account_name}
                        {manyHolders && t.account_holder && ` (${t.account_holder})`} · {t.split ? "פיצול" : categoryLabel(t.category_name)}
                      </span>
                    </span>
                    <Amount value={t.amount} className="shrink-0 font-bold" />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}

        {cursor && (
          <button type="button" onClick={loadMore} className="btn-ghost self-center">
            טעינת עוד
          </button>
        )}
      </div>
      {sheet && <TxnSheet key={sheet.id} t={sheet} onClose={() => setSheet(null)} />}
    </HomeContext>
  );
}
