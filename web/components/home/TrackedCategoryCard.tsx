"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { searchHref } from "@/lib/search";
import { Card } from "@/components/Card";
import { CategorySelect, loadCategories } from "@/components/CategorySelect";
import { send } from "@/lib/api";
import { categoryLabel } from "@/lib/format";
import { mapTxns, txnKey, type HomeData, type TrackedCategory } from "@/lib/home";
import { useHome } from "./context";
import { Expander } from "./Expander";
import { HistorySheet } from "./HistorySheet";
import { Menu, SpentHeader } from "./parts";
import { TxnList, TxnRow } from "./TxnRow";
import { WeekTable } from "./WeekTable";

type Panel = "history" | "amount" | "move" | null;

export function TrackedCategoryCard({ c }: { c: TrackedCategory }) {
  const { data, mutate } = useHome();
  const router = useRouter();
  const [panel, setPanel] = useState<Panel>(null);
  const id = c.category_id;
  const cycle_start = data.cycle.start;
  const patch = (fn: (c: TrackedCategory) => TrackedCategory) => (d: HomeData) => ({ ...d, tracked: d.tracked.map((x) => (x.category_id === id ? fn(x) : x)) });
  // Optimistically moved transactions drop out right away (totals follow on refetch).
  const txns = c.transactions.filter((t) => t.category_id === id);
  const weekly = c.mode === "weekly" && c.weeks;
  const name = categoryLabel(c.name);

  const menu = (
        <Menu
          label={`אפשרויות עבור ${name}`}
          items={[
            { label: "חודשים קודמים", onSelect: () => setPanel("history") },
            { label: "כל העסקאות בקטגוריה", onSelect: () => router.push(searchHref({ category_id: id })) },
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

  // RiseUp-style card: name + ⋮, "יצא" vs "צפוי לצאת" with a bar, what's left; weeks / transactions collapsed below.
  return (
    <Card title={name} action={menu} className="gap-0! pb-0!">
      <div className="pt-3 pb-4">
        <SpentHeader spent={c.spent} expected={c.expected} tone="category" />
      </div>
      <Expander className="-mx-4 border-t border-hairline px-3" buttonClassName="flex min-h-12 px-2" label={<span className="text-sm font-bold">{weekly ? "פירוט שבועי" : "פירוט חודשי"}</span>}>
        <div className="px-1 pb-2">
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
      {panel === "history" && <HistorySheet kind="category" categoryId={id} title={name} labels={["יצא", "צפוי"]} onClose={() => setPanel(null)} />}
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
    </Card>
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

function AmountEdit({ c, onClose, onSave }: { c: TrackedCategory; onClose: () => void; onSave: (amount: number | null) => void }) {
  const [value, setValue] = useState(String(c.expected));
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
