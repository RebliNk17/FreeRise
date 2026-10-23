"use client";

import { useEffect, useRef, useState } from "react";
import { CalendarClock, ChevronLeft, EyeOff, PiggyBank, Repeat, StickyNote, Tag, Wallet, X } from "lucide-react";
import { Money } from "@/components/Amount";
import { CategorySelect, GROUP_LABEL, loadCategories } from "@/components/CategorySelect";
import { send, type Category, type Group } from "@/lib/api";
import { categoryLabel, formatDate } from "@/lib/format";
import { mapTxns, type Txn } from "@/lib/home";
import { useHome } from "./context";

const CHIP: Partial<Record<Group, string>> = {
  variable: "bg-brand-soft text-brand",
  fixed: "bg-sun-soft text-text",
  savings: "bg-brand-soft text-brand",
  income: "bg-brand-soft text-brand",
};

/** Two-letter avatar from the merchant name ("שופרסל דיל" → "שד"). */
const initials = (s: string) =>
  s
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("");

type Action = { icon: React.ReactNode; label: string; run: () => void; value?: string | null; tone?: "sun" | "danger" };

const IGNORE_CATEGORY = "להתעלם";

type Mode = null | "note" | "fixed" | "cycle" | { groups: Group[]; title: string; remember: boolean };

/** Bottom sheet (native modal <dialog>: focus trap + Escape); backdrop tap or swipe-down closes too. */
export function TxnSheet({ t, onClose }: { t: Txn; onClose: () => void }) {
  const { mutate, data } = useHome();
  const ref = useRef<HTMLDialogElement>(null);
  const [mode, setMode] = useState<Mode>(null);
  const [dy, setDy] = useState<number | null>(null);
  const startY = useRef<number | null>(null);

  useEffect(() => {
    const d = ref.current!;
    const opener = document.activeElement as HTMLElement | null;
    d.showModal();
    return () => {
      d.close();
      opener?.focus();
    };
  }, []);

  async function setCategory(category_id: number, remember: boolean) {
    const c = (await loadCategories().catch(() => [] as Category[])).find((x) => x.id === category_id);
    onClose();
    mutate(
      (d) => mapTxns(d, (x) => (x.id === t.id ? (c?.group === "ignore" ? null : { ...x, category_id, category_name: c?.name ?? null, group: c?.group ?? x.group }) : x)),
      () => send("PUT", `/transactions/${t.id}/category`, { category_id, remember, apply_to_past: false }),
    );
  }

  async function ignore() {
    const c = (await loadCategories().catch(() => [] as Category[])).find((x) => x.name === IGNORE_CATEGORY);
    if (c) return setCategory(c.id, false);
    onClose();
    mutate((d) => d, () => Promise.reject(new Error(`no "${IGNORE_CATEGORY}" category`))); // surfaces the failure banner
  }

  const actions: Action[] = [];
  // Moved out of the current cycle into one home can't open yet: undo is the first thing offered.
  if (data.moved_next.transactions.some((x) => x.id === t.id)) actions.push({ icon: <CalendarClock size={18} />, label: "החזר לחודש הזה", run: () => cycle("own")() });
  actions.push(
    { icon: <Tag size={18} />, label: "שינוי קטגוריה", value: categoryLabel(t.category_name), run: () => setMode({ groups: Object.keys(GROUP_LABEL) as Group[], title: "שינוי קטגוריה", remember: true }) },
    { icon: <StickyNote size={18} />, label: t.note ? "עריכת הערה" : "הוספת הערה", tone: "sun", run: () => setMode("note") },
  );
  if (t.group === "fixed") actions.push({ icon: <Repeat size={18} />, label: "זו לא הוצאה קבועה", run: () => setMode({ groups: ["variable"], title: "לאיזו קטגוריה משתנה?", remember: true }) });
  if (t.group === "variable") actions.push({ icon: <Repeat size={18} />, label: "זו הוצאה קבועה", run: () => setMode({ groups: ["fixed"], title: "לאיזו קטגוריה קבועה?", remember: true }) });
  // The sheet's one primary action (full-width button under the list).
  const primary: Action | null =
    t.group !== "savings" && t.group !== "income" ? { icon: <PiggyBank size={18} />, label: "זו הפקדה לחיסכון", run: () => setMode({ groups: ["savings"], title: "לאיזה חיסכון?", remember: true }) } : null;
  if (t.amount > 0 && (t.group === "income" || t.group === null)) {
    const id = t.fixed_income_id;
    if (id != null) actions.push({ icon: <Wallet size={18} />, label: "זו לא הכנסה קבועה", run: () => request((x) => ({ ...x, fixed_income_id: null }), () => send("DELETE", `/recurring/${id}/fixed`)) });
    else actions.push({ icon: <Wallet size={18} />, label: "זו הכנסה קבועה", run: () => setMode("fixed") });
  }
  // previous/next are relative to the month the transaction actually happened in.
  const cycle = (target: "previous" | "next" | "own" | "auto") => () => request((x) => x, () => send("PUT", `/transactions/${t.id}/cycle`, { target }));
  const cycleOptions: Action[] = [];
  if (t.cycle_shift !== "previous") cycleOptions.push({ icon: <CalendarClock size={18} />, label: "שייך לחודש הקודם", run: cycle("previous") });
  if (t.cycle_shift !== "next") cycleOptions.push({ icon: <CalendarClock size={18} />, label: "שייך לחודש הבא", run: cycle("next") });
  if (t.cycle_shift) cycleOptions.push({ icon: <CalendarClock size={18} />, label: "שייך לחודש שבו נכנסה", run: cycle("own") });
  if (t.cycle_date_source === "manual") cycleOptions.push({ icon: <CalendarClock size={18} />, label: "שיוך אוטומטי", run: cycle("auto") });
  actions.push({ icon: <CalendarClock size={18} />, label: "שיוך לחודש", value: t.cycle_shift ? t.cycle_label : t.cycle_date_source === "manual" ? "ידני" : "אוטומטי", run: () => setMode("cycle") });
  actions.push({ icon: <EyeOff size={18} />, label: "להוציא מהתזרים", tone: "danger", run: ignore });

  /** Close, apply `optimistic` to this txn, run `req`; the home refetch places it right. */
  function request(optimistic: (x: Txn) => Txn, req: () => Promise<unknown>) {
    onClose();
    mutate((d) => mapTxns(d, (x) => (x.id === t.id ? optimistic(x) : x)), req);
  }

  const swipe = {
    onPointerDown: (e: React.PointerEvent) => void (startY.current = e.clientY),
    onPointerMove: (e: React.PointerEvent) => startY.current != null && setDy(Math.max(0, e.clientY - startY.current)),
    onPointerUp: () => {
      startY.current = null;
      if ((dy ?? 0) > 80) onClose();
      setDy(null);
    },
    onPointerCancel: () => ((startY.current = null), setDy(null)),
  };

  return (
    <dialog
      ref={ref}
      aria-labelledby="txn-sheet-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => e.target === ref.current && onClose()}
      style={dy != null ? { translate: `0 ${dy}px`, transition: "none" } : undefined}
      className="mx-auto mt-auto mb-0 max-h-[90dvh] w-full max-w-lg overflow-hidden rounded-t-[28px] border-0 bg-bg p-0 text-text shadow-[0_-10px_40px_rgb(0_0_0/0.25)] transition-[translate] duration-300 ease-out backdrop:bg-(--backdrop) starting:translate-y-full motion-reduce:transition-none"
    >
      <div className="flex max-h-[90dvh] flex-col">
        <header className="flex touch-none flex-col gap-3.5 px-5 pt-2.5 pb-4" {...swipe}>
          <div className="mx-auto h-[5px] w-11 rounded-full bg-border" aria-hidden />
          <div className="flex items-center gap-2">
            <p className={`chip min-w-0 truncate px-3 py-1.5 text-[13px] ${CHIP[t.group ?? "variable"] ?? "bg-sunken text-text"}`}>
              {t.group ? GROUP_LABEL[t.group] : "לא מסווג"} · {categoryLabel(t.category_name)}
            </p>
            <button type="button" className="icon-btn ms-auto size-9" aria-label="סגירה" onClick={onClose}>
              <X size={18} />
            </button>
          </div>
          <div className="flex items-center gap-3.5">
            <span aria-hidden className="flex size-14 shrink-0 items-center justify-center rounded-[18px] bg-surface font-display text-lg font-extrabold text-brand shadow-card">
              {initials(t.description)}
            </span>
            <div className="min-w-0 flex-1">
              <h2 id="txn-sheet-title" className="truncate font-display text-[19px] font-bold">
                {t.description}
              </h2>
              <p className="text-[13px] text-muted">
                <span dir="ltr">{formatDate(t.date)}</span> · {t.account_label}
                {t.account_holder && ` · על שם ${t.account_holder}`}
                {t.cycle_label && ` · שויך ל${t.cycle_label}`}
                {t.installment_total ? ` · תשלום ${t.installment_number}/${t.installment_total}` : ""}
              </p>
            </div>
          </div>
          <Money value={Math.abs(t.amount)} className="block text-right text-[46px] leading-none font-extrabold" />
        </header>
        <div className="overflow-y-auto px-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
          {t.note && mode !== "note" && <p className="mb-3 rounded-2xl bg-sun-soft p-3 text-sm whitespace-pre-wrap">{t.note}</p>}
          {mode === "note" ? (
            <NoteForm
              initial={t.note ?? ""}
              onCancel={() => setMode(null)}
              onSave={(note) => {
                setMode(null);
                mutate(
                  (d) => mapTxns(d, (x) => (x.id === t.id ? { ...x, note } : x)),
                  () => send("PUT", `/transactions/${t.id}/note`, { note }),
                );
              }}
            />
          ) : mode === "cycle" ? (
            <div className="flex flex-col gap-3">
              <h3 className="px-1 font-bold">לאיזה חודש לשייך?</h3>
              <ActionList items={cycleOptions} />
              <button type="button" className="btn-ghost" onClick={() => setMode(null)}>
                חזרה
              </button>
            </div>
          ) : mode === "fixed" ? (
            <FixedIncomeForm
              day={Number(t.date.slice(8, 10))}
              onCancel={() => setMode(null)}
              onSave={(expected_day, expected_amount) => request((x) => x, () => send("POST", `/transactions/${t.id}/fixed-income`, { expected_day, expected_amount }))}
            />
          ) : mode ? (
            <CategoryForm key={mode.title} {...mode} current={t.category_id} onCancel={() => setMode(null)} onSave={setCategory} />
          ) : (
            <>
              <ActionList items={actions} />
              {primary && (
                <button type="button" className="btn mt-3.5 min-h-[50px] w-full rounded-2xl text-[15px]" onClick={primary.run}>
                  {primary.icon}
                  {primary.label}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </dialog>
  );
}

function NoteForm({ initial, onSave, onCancel }: { initial: string; onSave: (note: string | null) => void; onCancel: () => void }) {
  const [value, setValue] = useState(initial);
  return (
    <form
      className="card flex flex-col gap-3 p-3.5"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(value.trim() || null);
      }}
    >
      <textarea className="input min-h-24" value={value} onChange={(e) => setValue(e.target.value)} aria-label="הערה" maxLength={500} autoFocus />
      <div className="flex gap-2">
        <button className="btn flex-1">שמירה</button>
        <button type="button" className="btn-ghost" onClick={onCancel}>
          ביטול
        </button>
      </div>
    </form>
  );
}

function CategoryForm({ groups, title, remember: rememberDefault, current, onSave, onCancel }: { groups: Group[]; title: string; remember: boolean; current: number | null; onSave: (id: number, remember: boolean) => void; onCancel: () => void }) {
  const [cat, setCat] = useState<number | null>(null);
  const [remember, setRemember] = useState(rememberDefault);
  return (
    <form
      className="card flex flex-col gap-3 p-3.5"
      onSubmit={(e) => {
        e.preventDefault();
        if (cat != null) onSave(cat, remember);
      }}
    >
      <h3 className="font-bold">{title}</h3>
      <CategorySelect value={cat} onChange={setCat} groups={groups} exclude={current} autoFocus />
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
        לזכור לבית העסק הזה בפעם הבאה
      </label>
      <div className="flex gap-2">
        <button className="btn flex-1" disabled={cat == null}>
          שמירה
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel}>
          ביטול
        </button>
      </div>
    </form>
  );
}

function FixedIncomeForm({ day: initialDay, onSave, onCancel }: { day: number; onSave: (day: number, amount: number | null) => void; onCancel: () => void }) {
  const [day, setDay] = useState(String(initialDay));
  const [amount, setAmount] = useState("");
  const d = Number(day);
  const ok = Number.isInteger(d) && d >= 1 && d <= 31;
  return (
    <form
      className="card flex flex-col gap-3 p-3.5"
      onSubmit={(e) => {
        e.preventDefault();
        if (ok) onSave(d, amount ? Number(amount) : null);
      }}
    >
      <h3 className="font-bold">הכנסה קבועה</h3>
      <p className="text-sm text-muted">נצפה לה בכל חודש. אם תגיע כמה ימים לפני או אחרי, היא תשויך לחודש שחסרה בו.</p>
      <label className="flex flex-col gap-1 text-sm">
        באיזה יום בחודש היא נכנסת בדרך כלל?
        <input className="input" dir="ltr" type="number" inputMode="numeric" min={1} max={31} value={day} onChange={(e) => setDay(e.target.value)} autoFocus />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        סכום צפוי (לא חובה, אחרת לפי ההכנסות האחרונות)
        <input className="input" dir="ltr" type="number" inputMode="decimal" min={1} step="any" value={amount} onChange={(e) => setAmount(e.target.value)} />
      </label>
      <div className="flex gap-2">
        <button className="btn flex-1" disabled={!ok}>
          שמירה
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel}>
          ביטול
        </button>
      </div>
    </form>
  );
}

const TONE = { brand: "bg-brand-soft text-brand", sun: "bg-sun-soft text-sun-strong", danger: "bg-danger-soft text-danger" };

function ActionList({ items }: { items: Action[] }) {
  return (
    <ul className="card flex flex-col divide-y divide-hairline overflow-hidden rounded-[22px]">
      {items.map((a) => (
        <li key={a.label}>
          <button type="button" className={`flex min-h-14 w-full items-center gap-3 px-4 py-3 text-start text-[15px] hover:bg-sunken/60 ${a.tone === "danger" ? "text-danger" : ""}`} onClick={a.run}>
            <span className={`flex size-[34px] shrink-0 items-center justify-center rounded-[11px] ${TONE[a.tone ?? "brand"]}`}>{a.icon}</span>
            <span className="flex-1">{a.label}</span>
            {a.value && <span className="max-w-[40%] truncate text-[13px] text-faint">{a.value}</span>}
            <ChevronLeft size={16} className="shrink-0 text-faint" aria-hidden />
          </button>
        </li>
      ))}
    </ul>
  );
}
