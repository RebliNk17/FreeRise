"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Check, Pencil, Plus, Trash2, PartyPopper } from "lucide-react";
import { Amount } from "@/components/Amount";
import { Card, ProgressBar, Status, EmptyState } from "@/components/Card";
import { send, type SavingsPlan, type SavingsPlans } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function PlansPage() {
  return (
    <Suspense>
      <Plans />
    </Suspense>
  );
}

function Plans() {
  const { data, error, reload } = useApi<SavingsPlans>("/plans");
  // /plans?monthly=2400 (home's "יש לכם מקום לחסוך" card) opens a new plan for that monthly amount.
  const monthly = Number(useSearchParams().get("monthly")) || undefined;
  const [editing, setEditing] = useState<SavingsPlan | "new" | null>(monthly ? "new" : null);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="page-title">יעדי חיסכון</h1>
      <Status loading={!data} error={error} />
      {data && (
        <>
          <Card>
            <p className="text-sm text-muted">כמה לשים בצד כל חודש?</p>
            <Amount value={data.monthly_total} plain className="text-[40px] leading-tight font-extrabold" />
            <p className="text-sm text-muted">
              {data.active_count === 1 ? "תוכנית פעילה אחת" : `${data.active_count} תוכניות פעילות`} · הסכום נכלל ביעד החודשי בעמוד הבית
            </p>
          </Card>

          {editing === "new" ? (
            <PlanForm monthly={monthly} onDone={() => {
                setEditing(null);
                reload();
              }} onCancel={() => setEditing(null)} />
          ) : (
            <button className="btn self-start" onClick={() => setEditing("new")}>
              <Plus size={18} /> תוכנית חדשה
            </button>
          )}

          {data.plans.length === 0 && <EmptyState text="עוד אין תוכניות. מה תרצו לחסוך?" />}
          {data.plans.map((p) =>
            editing !== "new" && editing?.id === p.id ? (
              <PlanForm key={p.id} plan={p} onDone={() => {
                setEditing(null);
                reload();
              }} onCancel={() => setEditing(null)} />
            ) : (
              <PlanCard key={p.id} plan={p} onEdit={() => setEditing(p)} onChanged={reload} />
            ),
          )}
        </>
      )}
    </div>
  );
}

function PlanCard({ plan: p, onEdit, onChanged }: { plan: SavingsPlan; onEdit: () => void; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const pct = p.target_amount > 0 ? Math.min(100, (p.saved_amount / p.target_amount) * 100) : 0;

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      setError(false);
      onChanged();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title={p.name}
      className={p.active ? "" : "opacity-60"}
      action={
        <>
          <button className="flex size-9 items-center justify-center rounded-xl text-muted hover:bg-sunken hover:text-text" aria-label={`עריכת ${p.name}`} onClick={onEdit}>
            <Pencil size={16} />
          </button>
          <button className="flex size-9 items-center justify-center rounded-xl text-muted hover:bg-danger-soft hover:text-danger" aria-label={`מחיקת ${p.name}`} disabled={busy} onClick={() => {
              if (confirm(`למחוק את "${p.name}"?`)) act(() => send("DELETE", `/plans/${p.id}`));
            }}>
            <Trash2 size={16} />
          </button>
        </>
      }
    >
      <div className="flex items-baseline justify-between text-sm">
        <span>
          נחסכו <Amount value={p.saved_amount} plain className="font-bold" />
        </span>
        <span className="text-muted">
          מתוך <Amount value={p.target_amount} plain />
        </span>
      </div>
      <ProgressBar percent={pct} label={`התקדמות ${p.name}`} />
      {p.completed ? (
        <div className="flex items-center gap-3">
          <p className="flex flex-1 items-center gap-1.5 text-sm font-semibold text-positive">
            <PartyPopper size={16} aria-hidden /> הגעתם ליעד
          </p>
          {p.funded_this_cycle && (
            <button className="btn-ghost" disabled={busy} onClick={() => act(() => send("DELETE", `/plans/${p.id}/contribute`))}>
              ביטול ההעברה של החודש
            </button>
          )}
        </div>
      ) : (
        <>
          <p className="text-sm text-muted">
            עד <span dir="ltr">{formatDate(p.target_date)}</span>
            {!p.overdue && (p.months_left === 1 ? " · חודש אחרון" : ` · עוד ${p.months_left} חודשים`)}
            {!p.active && " · מושהית"}
            {p.overdue && <span className="font-semibold text-danger"> · עבר המועד (לא נכלל ביעד החודשי)</span>}
          </p>
          <div className="flex items-center gap-3">
            <span className="flex-1 text-sm">
              החודש: <Amount value={p.monthly_needed} plain className="font-bold" />
              {p.monthly_override != null && <span className="text-xs text-muted"> (סכום קבוע)</span>}
            </span>
            {p.funded_this_cycle ? (
              <>
                <span className="flex items-center gap-1 text-sm text-positive">
                  <Check size={16} /> הופרש החודש
                </span>
                <button className="btn-ghost" disabled={busy} onClick={() => act(() => send("DELETE", `/plans/${p.id}/contribute`))}>
                  ביטול
                </button>
              </>
            ) : (
              p.active && (
                <button className="btn" disabled={busy} onClick={() => act(() => send("POST", `/plans/${p.id}/contribute`))}>
                  העברתי החודש
                </button>
              )
            )}
          </div>
        </>
      )}
      {error && <p className="text-sm text-danger" role="alert">הפעולה נכשלה.</p>}
    </Card>
  );
}

/** `monthly` (new plans only): a year of that amount, set as the fixed monthly sum. */
function PlanForm({ plan, monthly, onDone, onCancel }: { plan?: SavingsPlan; monthly?: number; onDone: () => void; onCancel: () => void }) {
  const [name, setName] = useState(plan?.name ?? (monthly ? "חיסכון חודשי" : ""));
  const [target, setTarget] = useState(plan ? String(plan.target_amount) : monthly ? String(+(monthly * 12).toFixed(2)) : "");
  const [date, setDate] = useState(plan?.target_date ?? (monthly ? inAYear() : ""));
  const [saved, setSaved] = useState(String(plan?.saved_amount ?? 0));
  const [override, setOverride] = useState(plan?.monthly_override != null ? String(plan.monthly_override) : monthly ? String(monthly) : "");
  const [active, setActive] = useState(plan?.active ?? true);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    const body = {
      name: name.trim(),
      target_amount: Number(target),
      target_date: date,
      saved_amount: Number(saved) || 0,
      monthly_override: override.trim() ? Number(override) : null,
      active,
    };
    setBusy(true);
    try {
      await (plan ? send("PATCH", `/plans/${plan.id}`, body) : send("POST", "/plans", body));
      onDone();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title={plan ? "עריכת תוכנית" : "תוכנית חדשה"}>
      <form onSubmit={save} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1.5 text-[13px] text-muted">
          למה חוסכים?
          <input className="input" required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} placeholder="למשל: טיול משפחתי" autoFocus />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1.5 text-[13px] text-muted">
            סכום היעד
            <input className="input" type="number" required min={1} step="any" inputMode="numeric" dir="ltr" value={target} onChange={(e) => setTarget(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] text-muted">
            עד מתי
            <input className="input" type="date" required dir="ltr" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] text-muted">
            כבר נחסך
            <input className="input" type="number" min={0} step="any" inputMode="numeric" dir="ltr" value={saved} onChange={(e) => setSaved(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] text-muted">
            סכום חודשי קבוע (רשות)
            <input className="input" type="number" min={1} step="any" inputMode="numeric" dir="ltr" value={override} onChange={(e) => setOverride(e.target.value)} placeholder="חישוב אוטומטי" />
          </label>
        </div>
        {plan && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> תוכנית פעילה (נכללת ביעד החודשי)
          </label>
        )}
        <div className="flex gap-2">
          <button className="btn" disabled={busy}>
            שמירה
          </button>
          <button type="button" className="btn-ghost" onClick={onCancel}>
            ביטול
          </button>
        </div>
        {error && <p className="text-sm text-danger" role="alert">השמירה נכשלה. כדאי לבדוק את הסכומים והתאריך.</p>}
      </form>
    </Card>
  );
}

/** Local date a year from today, as the date input wants it (YYYY-MM-DD). */
function inAYear() {
  const d = new Date();
  d.setFullYear(d.getFullYear() + 1);
  return d.toLocaleDateString("en-CA");
}
