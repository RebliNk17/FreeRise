"use client";

import { useState } from "react";
import { Plus, RotateCcw, Trash2 } from "lucide-react";
import { Amount } from "@/components/Amount";
import { Card, Status } from "@/components/Card";
import { categoryLabel } from "@/lib/format";
import { PLAN_GROUPS, planTotals, toLines, type PlanGroup, type PlanLine, type TypicalMonth } from "@/lib/planner";
import { useApi } from "@/lib/useApi";

const TITLE: Record<PlanGroup, string> = { income: "הכנסות", fixed: "הוצאות קבועות", savings: "הפקדות לחיסכון", variable: "הוצאות משתנות" };
let seq = 0;

/** "חודש טיפוסי": averages of the last months, every amount editable, lines can be added; nothing is saved. */
export function Planner() {
  const { data, error } = useApi<TypicalMonth>("/whatif/typical");
  const [edited, setEdited] = useState<PlanLine[] | null>(null);
  if (!data) return <Status loading={!error} error={error} />;
  const lines = edited ?? toLines(data).map((l) => ({ ...l, label: categoryLabel(l.label) }));
  const t = planTotals(lines, data.goal);
  const set = (key: string, patch: Partial<PlanLine>) => setEdited(lines.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  return (
    <Card
      title="חודש טיפוסי"
      action={
        edited && (
          <button type="button" className="btn-ghost" onClick={() => setEdited(null)}>
            <RotateCcw size={14} aria-hidden /> איפוס
          </button>
        )
      }
    >
      <p className="text-sm text-muted">
        {data.months ? `ממוצע ${data.months} החודשים האחרונים לפי קטגוריה.` : "אין עדיין חודשים קודמים, אפשר להוסיף שורות."} משנים כל סכום או מוסיפים שורות ורואים איך ייגמר חודש כזה.
      </p>
      <div className="grid grid-cols-2 gap-2" aria-live="polite">
        <div className="rounded-2xl bg-sunken p-3">
          <span className="block text-xs text-muted">סוף החודש</span>
          <Amount value={t.month_end} plain className={`text-2xl font-extrabold ${t.month_end < 0 ? "text-danger" : ""}`} />
        </div>
        <div className="rounded-2xl bg-sunken p-3">
          <span className="block text-xs text-muted">תקציב שבועי</span>
          <Amount value={t.weekly_allowance} plain className={`text-2xl font-extrabold ${t.weekly_allowance < 0 ? "text-danger" : ""}`} />
        </div>
      </div>
      <p className="text-xs text-muted">
        סוף החודש = הכנסות − קבועות − חיסכון − משתנות. תקציב שבועי = (הכנסות − קבועות − חיסכון − יעד <Amount value={data.goal} plain />) ÷ {(30.44 / 7).toFixed(1)} שבועות.
      </p>
      {PLAN_GROUPS.map((g) => {
        const rows = lines.filter((l) => l.group === g);
        return (
          <section key={g} className="flex flex-col gap-2 border-t border-hairline pt-3">
            <div className="flex items-center gap-2">
              <h3 className="flex-1 font-bold">{TITLE[g]}</h3>
              <Amount value={t[g]} plain className="font-bold" />
            </div>
            <ul className="flex flex-col gap-2">
              {rows.map((l) => (
                <li key={l.key} className="flex items-center gap-2">
                  <input className="input min-w-0 flex-1" value={l.label} onChange={(e) => set(l.key, { label: e.target.value })} placeholder="שם השורה" aria-label={`שם שורה ב${TITLE[g]}`} maxLength={60} />
                  <input className="input w-28 shrink-0" type="number" min={0} step="any" inputMode="decimal" dir="ltr" value={l.amount} onChange={(e) => set(l.key, { amount: e.target.value })} aria-label={`סכום ${l.label || "שורה"}`} />
                  <button type="button" className="icon-btn size-11" aria-label={`הסרת ${l.label || "השורה"}`} onClick={() => setEdited(lines.filter((x) => x.key !== l.key))}>
                    <Trash2 size={16} />
                  </button>
                </li>
              ))}
            </ul>
            <button type="button" className="btn-ghost self-start" onClick={() => setEdited([...lines, { key: `n${++seq}`, group: g, label: "", amount: "" }])}>
              <Plus size={14} aria-hidden /> שורה
            </button>
          </section>
        );
      })}
    </Card>
  );
}
