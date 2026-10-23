"use client";

import { useEffect, useState } from "react";
import { Minus, Plus, Trash2 } from "lucide-react";
import { Amount } from "@/components/Amount";
import { Card, Status } from "@/components/Card";
import { api, type Recurring, type WhatIf, type WhatIfNumbers } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Planner } from "./Planner";

const CADENCE_MONTHS: Record<string, number> = { monthly: 1, bimonthly: 2, quarterly: 3, semiannual: 6, annual: 12 };
/** Monthly equivalent of a recurring charge (an annual ₪1,200 → ₪100). */
const monthly = (r: Recurring) => Math.round((r.expected_amount / (CADENCE_MONTHS[r.cadence] ?? 1)) * 100) / 100;

type Row = { key: string; label: string; amount: string; income: boolean; preset?: number };

const ROWS: { field: keyof WhatIfNumbers; label: string }[] = [
  { field: "variable_allowance", label: "תקציב להוצאות משתנות" },
  { field: "weekly_left", label: "נשאר להוציא השבוע" },
  { field: "month_end", label: "צפי לסוף החודש" },
];

let seq = 0;

export default function WhatIfPage() {
  const { data: recurring, error } = useApi<Recurring[]>("/recurring?status=confirmed");
  const [rows, setRows] = useState<Row[]>([]);
  const [result, setResult] = useState<WhatIf | null>(null);
  const [failed, setFailed] = useState(false);

  const changes = rows
    .map((r) => ({ label: r.label || "שינוי", monthly_amount: (r.income ? 1 : -1) * Math.abs(Number(r.amount) || 0) }))
    .filter((c) => c.monthly_amount !== 0);
  const body = JSON.stringify({ changes });

  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      api<WhatIf>("/whatif", { method: "POST", body })
        .then((r) => {
          if (!live) return;
          setResult(r);
          setFailed(false);
        })
        .catch(() => live && setFailed(true));
    }, 250);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [body]);

  const update = (key: string, patch: Partial<Row>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const remove = (key: string) => setRows((rs) => rs.filter((r) => r.key !== key));
  const addCustom = () => setRows((rs) => [...rs, { key: `c${++seq}`, label: "", amount: "", income: false }]);
  const togglePreset = (r: Recurring) =>
    setRows((rs) => (rs.some((x) => x.preset === r.id) ? rs.filter((x) => x.preset !== r.id) : [...rs, { key: `p${r.id}`, label: `לבטל את ${r.label}`, amount: String(monthly(r)), income: true, preset: r.id }]));

  const expenses = (recurring ?? []).filter((r) => r.direction === "expense");

  return (
    <div className="flex flex-col gap-4">
      <h1 className="page-title">תרחישים</h1>
      <p className="text-sm text-muted">מנסים שינוי חודשי ורואים איך הוא משפיע על החודש הנוכחי ועל השנה. שום דבר לא נשמר.</p>

      {expenses.length > 0 && (
        <Card title="ואם נבטל...">
          <div className="flex flex-wrap gap-2">
            {expenses.map((r) => {
              const on = rows.some((x) => x.preset === r.id);
              return (
                <button key={r.id} aria-pressed={on} className={`btn-ghost ${on ? "border-brand bg-brand/10 text-brand" : ""}`} onClick={() => togglePreset(r)}>
                  {r.label} · <Amount value={monthly(r)} plain />
                </button>
              );
            })}
          </div>
        </Card>
      )}
      {error && <Status loading={false} error />}

      <Card title="השינויים שלי" action={<button className="btn-ghost" onClick={addCustom}><Plus size={14} /> שינוי</button>}>
        {rows.length === 0 && <p className="text-sm text-muted">בחרו חיוב לביטול או הוסיפו שינוי משלכם — הוצאה חדשה, העלאה במשכורת, חיסכון.</p>}
        <ul className="flex flex-col gap-2">
          {rows.map((r) => (
            <li key={r.key} className="flex items-center gap-2">
              <button
                className={`btn-ghost w-10 shrink-0 px-0 ${r.income ? "text-positive" : "text-danger"}`}
                aria-label={r.income ? "תוספת בחודש (לחצו להפוך להוצאה)" : "הוצאה בחודש (לחצו להפוך לתוספת)"}
                onClick={() => update(r.key, { income: !r.income })}
              >
                {r.income ? <Plus size={16} /> : <Minus size={16} />}
              </button>
              <input className="input min-w-0 flex-1" value={r.label} onChange={(e) => update(r.key, { label: e.target.value })} placeholder="מה משתנה?" aria-label="תיאור השינוי" maxLength={80} />
              <input className="input w-28 shrink-0" type="number" min={0} step="any" inputMode="numeric" dir="ltr" value={r.amount} onChange={(e) => update(r.key, { amount: e.target.value })} placeholder="בחודש" aria-label="סכום בחודש" />
              <button className="p-1 text-muted hover:text-danger" aria-label="הסרת השינוי" onClick={() => remove(r.key)}>
                <Trash2 size={16} />
              </button>
            </li>
          ))}
        </ul>
      </Card>

      {failed && <p className="text-danger" role="alert">החישוב נכשל.</p>}
      {result && (
        <>
          <Card>
            <p className="text-sm text-muted">בשנה זה יוצא</p>
            <Amount value={result.yearly_impact} className={`text-4xl font-bold ${result.yearly_impact < 0 ? "text-danger" : ""}`} />
            <p className="text-sm text-muted">
              <Amount value={result.monthly_delta} className={result.monthly_delta < 0 ? "text-danger" : ""} /> בחודש
            </p>
          </Card>
          <Card title="לפני ואחרי">
            <div className="grid grid-cols-[1fr_auto_auto] gap-x-4 gap-y-2 text-sm">
              <span />
              <span className="text-xs text-muted">היום</span>
              <span className="text-xs text-muted">עם השינוי</span>
              {ROWS.map(({ field, label }) => {
                const a = result.baseline[field];
                const b = result.scenario[field];
                return (
                  <div key={field} className="contents">
                    <span>{label}</span>
                    <Amount value={a} plain className={a < 0 ? "text-danger" : ""} />
                    <Amount value={b} plain className={`font-bold ${b < a ? "text-danger" : b > a ? "text-positive" : ""}`} />
                  </div>
                );
              })}
            </div>
            <p className="text-xs text-muted">
              תקציב להוצאות משתנות &quot;עם השינוי&quot; = התקציב היום ± השינוי החודשי, כלומר כמה תוכלו להוציא אם תתאימו את ההוצאות לשינוי.
            </p>
            <p className="text-xs text-muted">
              צפי לסוף החודש = הכנסות צפויות − קבועות צפויות − הוצאות משתנות לפי הקצב עד היום. &quot;עם השינוי&quot; = אותו צפי ± השינוי החודשי, בלי לשנות את קצב ההוצאות.
            </p>
          </Card>
        </>
      )}

      <Planner />
    </div>
  );
}
