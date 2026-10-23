"use client";

import { useState } from "react";
import { Money } from "@/components/Amount";
import { CategoryRing } from "@/components/CategoryIcon";
import { CategorySelect, loadCategories } from "@/components/CategorySelect";
import { send } from "@/lib/api";
import { categoryLabel, monthName } from "@/lib/format";
import { mapTxns, txnKey, type HomeData, type TrackedCategory } from "@/lib/home";
import { useHome } from "./context";
import { Expander } from "./Expander";
import { Menu } from "./parts";
import { TxnList, TxnRow } from "./TxnRow";
import { WeekTable } from "./WeekTable";

type Panel = "history" | "amount" | "move" | null;

export function TrackedCategoryCard({ c }: { c: TrackedCategory }) {
  const { data, mutate } = useHome();
  const [panel, setPanel] = useState<Panel>(null);
  const id = c.category_id;
  const cycle_start = data.cycle.start;
  const patch = (fn: (c: TrackedCategory) => TrackedCategory) => (d: HomeData) => ({ ...d, tracked: d.tracked.map((x) => (x.category_id === id ? fn(x) : x)) });
  // Optimistically moved transactions drop out right away (totals follow on refetch).
  const txns = c.transactions.filter((t) => t.category_id === id);
  const weekly = c.mode === "weekly" && c.weeks;
  const name = categoryLabel(c.name);
  const over = c.spent > c.expected + 0.005;

  const menu = (
        <Menu
          label={`אפשרויות עבור ${name}`}
          items={[
            { label: "חודשים קודמים", onSelect: () => setPanel("history") },
            { label: "עריכת סכום", onSelect: () => setPanel("amount") },
            { label: "העברת עסקאות", onSelect: () => setPanel("move") },
            {
              label: c.mode === "weekly" ? "שינוי לפירוט חודשי" : "שינוי לפירוט שבועי",
              onSelect: () => {
                const mode = c.mode === "weekly" ? "monthly" : "weekly";
                mutate(patch((x) => ({ ...x, mode })), () => send("PUT", `/tracking/${id}`, { tracked: true, mode }));
              },
            },
            {
              label: "הסרה מהמעקב",
              danger: true,
              onSelect: () =>
                mutate(
                  (d) => ({ ...d, tracked: d.tracked.filter((x) => x.category_id !== id), untracked_available: [...d.untracked_available, { category_id: id, name: c.name }] }),
                  () => send("PUT", `/tracking/${id}`, { tracked: false }),
                ),
            },
          ]}
        />
  );

  // Row: ring + name + what's left (or over) + spent; tap expands to weeks / transactions; ⋮ for the rest.
  return (
    <div className="flex flex-col">
      <Expander
        rowClassName="flex items-center gap-1"
        className="min-w-0"
        buttonClassName="flex min-h-15 min-w-0 flex-1 py-2.5"
        labelClassName="flex min-w-0 flex-1 items-center gap-3"
        aside={menu}
        chevron={false}
        label={
          <>
            <CategoryRing name={c.name} percent={c.expected > 0 ? (c.spent / c.expected) * 100 : c.spent > 0 ? 100 : 0} over={over} />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-bold">{name}</span>
              <span className={`block text-xs ${over ? "font-semibold text-danger" : "text-muted"}`}>
                {over ? (
                  <>
                    חריגה של <Money value={Math.round(c.spent - c.expected)} />
                  </>
                ) : (
                  <>
                    נשאר <Money value={Math.round(c.expected - c.spent)} /> מתוך <Money value={Math.round(c.expected)} />
                  </>
                )}
              </span>
            </span>
            <Money value={Math.round(c.spent)} className="shrink-0 font-bold" />
          </>
        }
      >
        <div className="pb-2">
          {weekly ? (
            <WeekTable
              weeks={c.weeks!.map((w) => ({ ...w, transactions: w.transactions.filter((t) => t.category_id === id) }))}
              col="expected"
              onEdit={(w, amount) =>
                mutate(
                  patch((x) => ({ ...x, weeks: x.weeks?.map((y) => (y.index === w.index ? { ...y, expected: amount ?? y.expected } : y)) ?? null })),
                  () => send("PUT", `/tracking/${id}/weeks`, { cycle_start, week_index: w.index, amount }),
                )
              }
            />
          ) : (
            <TxnList txns={txns} empty="אין עסקאות במחזור הזה" />
          )}
        </div>
      </Expander>
      {panel === "history" && <History c={c} onClose={() => setPanel(null)} />}
      {panel === "amount" && (
        <AmountEdit
          c={c}
          onClose={() => setPanel(null)}
          onSave={(amount) => {
            setPanel(null);
            mutate(patch((x) => ({ ...x, expected: amount ?? x.expected, expected_overridden: amount != null })), () => send("PUT", `/tracking/${id}/expected`, { cycle_start, amount }));
          }}
        />
      )}
      {panel === "move" && <MoveTxns c={c} txns={txns} onClose={() => setPanel(null)} />}
    </div>
  );
}

function PanelBox({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="mb-2.5 flex flex-col gap-3 rounded-2xl bg-bg p-3">
      <div className="flex items-center">
        <h3 className="flex-1 text-sm font-bold">{title}</h3>
        <button type="button" className="-my-2 min-h-9 px-1 text-xs font-semibold text-muted hover:text-text" onClick={onClose}>
          סגירה
        </button>
      </div>
      {children}
    </div>
  );
}

function History({ c, onClose }: { c: TrackedCategory; onClose: () => void }) {
  const max = Math.max(1, ...c.history.map((h) => h.spent));
  return (
    <PanelBox title="חודשים קודמים" onClose={onClose}>
      {c.history.length === 0 ? (
        <p className="text-sm text-muted">אין עדיין היסטוריה.</p>
      ) : (
        <ul className="flex h-32 items-end gap-2" aria-label={`הוצאות ${categoryLabel(c.name)} בחודשים קודמים`}>
          {c.history.map((h) => (
            <li key={`${h.label_year}-${h.label_month}`} className="flex h-full flex-1 flex-col items-center justify-end gap-1">
              <Money value={Math.round(h.spent)} className="text-[10px] text-muted" />
              <div className="w-full max-w-8 rounded-t-md bg-brand" style={{ height: `${(h.spent / max) * 70}%` }} />
              <span className="text-[11px] text-muted">{monthName(h.label_month).slice(0, 3)}</span>
            </li>
          ))}
        </ul>
      )}
    </PanelBox>
  );
}

function AmountEdit({ c, onClose, onSave }: { c: TrackedCategory; onClose: () => void; onSave: (amount: number | null) => void }) {
  const [value, setValue] = useState(String(Math.round(c.expected)));
  const [bad, setBad] = useState(false);
  return (
    <PanelBox title="כמה צפוי לצאת במחזור הזה?" onClose={onClose}>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const n = Number(value);
          if (value.trim() === "" || !Number.isFinite(n) || n < 0) return setBad(true);
          onSave(n);
        }}
      >
        <input type="number" min={0} step="any" inputMode="decimal" dir="ltr" className="input max-w-40" value={value} onChange={(e) => setValue(e.target.value)} aria-label="סכום צפוי" autoFocus onFocus={(e) => e.target.select()} />
        <button className="btn">שמירה</button>
        {c.expected_overridden && (
          <button type="button" className="btn-ghost" onClick={() => onSave(null)}>
            חזרה לחישוב אוטומטי
          </button>
        )}
      </form>
      {bad && <p className="text-sm text-danger" role="alert">יש להזין סכום חיובי.</p>}
    </PanelBox>
  );
}

function MoveTxns({ c, txns, onClose }: { c: TrackedCategory; txns: TrackedCategory["transactions"]; onClose: () => void }) {
  const { mutate } = useHome();
  const [sel, setSel] = useState<number[]>([]);
  const [cat, setCat] = useState<number | null>(null);
  const [remember, setRemember] = useState(false);

  async function move(e: React.FormEvent) {
    e.preventDefault();
    if (cat == null || !sel.length) return;
    const name = (await loadCategories().catch(() => [])).find((x) => x.id === cat)?.name ?? null;
    const ids = new Set(sel);
    onClose();
    mutate(
      (d) => mapTxns(d, (t) => (ids.has(t.id) ? { ...t, category_id: cat, category_name: name } : t)),
      () => send("POST", "/transactions/move", { ids: sel, category_id: cat, remember }),
    );
  }

  return (
    <PanelBox title="העברת עסקאות לקטגוריה אחרת" onClose={onClose}>
      <form onSubmit={move} className="flex flex-col gap-3">
        {txns.length === 0 ? (
          <p className="text-sm text-muted">אין עסקאות להעברה.</p>
        ) : (
          <ul className="flex max-h-72 flex-col divide-y divide-hairline overflow-y-auto">
            {txns.map((t) => (
              <li key={txnKey(t)}>
                <TxnRow t={t} select={{ checked: sel.includes(t.id), onChange: (v) => setSel((s) => (v ? [...s, t.id] : s.filter((x) => x !== t.id))) }} />
              </li>
            ))}
          </ul>
        )}
        <CategorySelect value={cat} onChange={setCat} exclude={c.category_id} label="קטגוריית יעד" />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          לזכור לפעם הבאה (לבית העסק)
        </label>
        <button className="btn" disabled={cat == null || !sel.length}>
          העברה{sel.length ? ` (${sel.length})` : ""}
        </button>
      </form>
    </PanelBox>
  );
}
