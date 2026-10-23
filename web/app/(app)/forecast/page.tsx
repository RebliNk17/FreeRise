"use client";

import { useState } from "react";
import { Amount } from "@/components/Amount";
import { Card, Status } from "@/components/Card";
import { ExpectedItems } from "@/components/ExpectedItems";
import { send, type Forecast, type Recurring } from "@/lib/api";
import { categoryLabel, formatCycleLabel, formatDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const CADENCE: Record<string, string> = { monthly: "חודשי", bimonthly: "דו-חודשי", quarterly: "רבעוני", semiannual: "חצי-שנתי", annual: "שנתי" };

export default function ForecastPage() {
  const { data: f, error, reload } = useApi<Forecast>("/forecast/next");
  // Confirming/dismissing changes the forecast and the fixed-income list; refetch both.
  const [version, setVersion] = useState(0);
  const empty = f && !f.fixed_items.length && !f.income_items.length && !f.installments_stopping.length;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="page-title">תחזית לחודש הבא{f && <span className="block text-sm font-normal text-muted">{formatCycleLabel(f.cycle.start, f.cycle.end)}</span>}</h1>
      <Status loading={!f} error={error} empty={empty} />
      {f && !empty && (
        <>
          <Card title={<>חודש הבא יפסיקו <Amount value={f.installments_stopping_total} plain /> תשלומים</>}>
            <ExpectedItems items={f.installments_stopping} none="אין תשלומים שמסתיימים." />
          </Card>
          <Card title="חיובים קבועים צפויים" action={<Amount value={f.fixed_total} plain className="font-bold" />}>
            {f.delta_fixed_vs_current !== 0 && (
              <p className="text-xs text-muted">
                {f.delta_fixed_vs_current > 0 ? "יותר" : "פחות"} מהחודש הנוכחי ב-<Amount value={Math.abs(f.delta_fixed_vs_current)} plain />
              </p>
            )}
            <ExpectedItems items={f.fixed_items} none="לא זוהו חיובים קבועים." />
          </Card>
          <Card title="הכנסות צפויות" action={<Amount value={f.income_total} plain className="font-bold text-positive" />}>
            <ExpectedItems income items={f.income_items} none="לא זוהו הכנסות קבועות." />
          </Card>
        </>
      )}
      <FixedIncomes key={version} onChange={reload} />
      <RecurringReview
        onChange={() => {
          reload();
          setVersion((v) => v + 1);
        }}
      />
    </div>
  );
}

function RecurringReview({ onChange }: { onChange: () => void }) {
  const { data, setData, error } = useApi<Recurring[]>("/recurring?status=pending");
  const [failed, setFailed] = useState(false);

  async function decide(r: Recurring, status: "confirmed" | "dismissed") {
    setData((d) => d?.filter((x) => x.id !== r.id));
    try {
      await send("PUT", `/recurring/${r.id}`, { status });
      setFailed(false);
      onChange();
    } catch {
      setData((d) => (d ? [r, ...d] : d));
      setFailed(true);
    }
  }

  if (error || !data?.length) return null;
  return (
    <Card title="חיובים קבועים שזוהו">
      {failed && <p className="text-sm text-danger" role="alert">העדכון נכשל.</p>}
      <ul className="flex flex-col divide-y divide-hairline text-sm">
        {data.map((r) => (
          <li key={r.id} className="flex flex-col gap-2 py-2">
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate font-bold">{r.label}</span>
                  {r.category_name && <span className="shrink-0 rounded-full bg-sunken px-2 py-0.5 text-xs font-semibold text-muted">{categoryLabel(r.category_name)}</span>}
                </div>
                <div className="text-xs text-muted">
                  {CADENCE[r.cadence] ?? r.cadence} · הבא <span dir="ltr">{formatDate(r.next_expected_date)}</span>
                </div>
                {r.account_label && (
                  <div className="text-xs text-muted">
                    {r.direction === "income" ? "נכנס ל" : "יורד מ"}: {r.account_label}
                    {r.previous_account_label && <span className="text-brand"> · עבר מ{r.previous_account_label}</span>}
                  </div>
                )}
                <div className="text-xs text-muted">{r.basis}</div>
              </div>
              <Amount value={r.direction === "income" ? r.expected_amount : -r.expected_amount} />
            </div>
            <div className="flex gap-2">
              <button className="btn flex-1 py-1.5" onClick={() => decide(r, "confirmed")}>
                אשר
              </button>
              <button className="btn-ghost flex-1" onClick={() => decide(r, "dismissed")}>
                לא קבוע
              </button>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function FixedIncomes({ onChange }: { onChange: () => void }) {
  const { data, setData, error, reload } = useApi<Recurring[]>("/recurring?status=confirmed");
  const [editing, setEditing] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  const items = data?.filter((r) => r.direction === "income" && r.cadence === "monthly");

  async function run(req: () => Promise<unknown>) {
    try {
      await req();
      setFailed(false);
    } catch {
      setFailed(true);
    }
    reload();
    onChange();
  }

  if (error || !items?.length) return null;
  return (
    <Card title="הכנסות קבועות">
      {failed && <p className="text-sm text-danger" role="alert">העדכון נכשל.</p>}
      <ul className="flex flex-col divide-y divide-hairline text-sm">
        {items.map((r) => {
          const day = r.expected_day ?? Number(r.next_expected_date.slice(8, 10));
          return (
            <li key={r.id} className="flex flex-col gap-2 py-2">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate font-bold">{r.label}</div>
                  <div className="text-xs text-muted">
                    בכל חודש ב-{day}
                    {r.account_label && ` · ${r.account_label}`}
                    {r.user_defined && " · הוגדרה על ידך"}
                  </div>
                </div>
                <Amount value={r.expected_amount} />
              </div>
              {editing === r.id ? (
                <FixedIncomeEdit
                  day={day}
                  amount={r.amount_kind === "fixed" ? r.expected_amount : null}
                  onCancel={() => setEditing(null)}
                  onSave={(expected_day, expected_amount) => {
                    setEditing(null);
                    run(() => send("PUT", `/recurring/${r.id}/fixed`, { expected_day, expected_amount }));
                  }}
                />
              ) : (
                <div className="flex gap-2">
                  <button className="btn-ghost flex-1" onClick={() => setEditing(r.id)}>
                    עריכה
                  </button>
                  <button
                    className="btn-ghost flex-1"
                    onClick={() => {
                      setData((d) => d?.filter((x) => x.id !== r.id));
                      run(() => send("DELETE", `/recurring/${r.id}/fixed`));
                    }}
                  >
                    לא הכנסה קבועה
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function FixedIncomeEdit({ day: d0, amount: a0, onSave, onCancel }: { day: number; amount: number | null; onSave: (day: number, amount: number | null) => void; onCancel: () => void }) {
  const [day, setDay] = useState(String(d0));
  const [amount, setAmount] = useState(a0 == null ? "" : String(a0));
  const d = Number(day);
  const ok = Number.isInteger(d) && d >= 1 && d <= 31;
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (ok) onSave(d, amount ? Number(amount) : null);
      }}
    >
      <div className="flex gap-2">
        <label className="flex flex-1 flex-col gap-1 text-xs text-muted">
          יום בחודש
          <input className="input" dir="ltr" type="number" inputMode="numeric" min={1} max={31} value={day} onChange={(e) => setDay(e.target.value)} />
        </label>
        <label className="flex flex-1 flex-col gap-1 text-xs text-muted">
          סכום צפוי (לא חובה)
          <input className="input" dir="ltr" type="number" inputMode="decimal" min={1} step="any" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
      </div>
      <div className="flex gap-2">
        <button className="btn flex-1 py-1.5" disabled={!ok}>
          שמירה
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel}>
          ביטול
        </button>
      </div>
    </form>
  );
}
