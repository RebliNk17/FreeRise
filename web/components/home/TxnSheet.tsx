"use client";

import { useState } from "react";
import { CalendarClock, Check, ChevronLeft, EyeOff, MessageCircleQuestion, PiggyBank, Plus, Repeat, Split, StickyNote, Tag, Trash2, Undo2, Wallet, X } from "lucide-react";
import { Money } from "@/components/Amount";
import { Sheet } from "@/components/Sheet";
import { Switch } from "@/components/Switch";
import { CategorySelect, GROUP_LABEL, loadCategories } from "@/components/CategorySelect";
import { send, type Category, type Group } from "@/lib/api";
import { categoryLabel, formatDate } from "@/lib/format";
import { splitBody, splitLeft, splitProblem, type SplitRow } from "@/lib/split";
import { mapTxns, type Txn } from "@/lib/home";
import { useApi } from "@/lib/useApi";
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

type Mode = null | "note" | "fixed" | "cycle" | "split" | "review" | { groups: Group[]; title: string; remember: boolean };

export function TxnSheet({ t, onClose }: { t: Txn; onClose: () => void }) {
  const { mutate, data } = useHome();
  const [mode, setMode] = useState<Mode>(null);
  const people = useApi<string[]>("/reviews/people").data ?? [];
  // "לבדוק עם <the other one>": anyone but this card's holder; one person → a shared "לבדיקה" flag.
  const other = people.length > 1 ? (people.find((p) => p !== t.account_holder) ?? people[0]) : null;

  /** all: also every past and future transaction of this merchant (rule + PUT /categories/merchant). */
  async function setCategory(category_id: number, all: boolean) {
    const c = (await loadCategories().catch(() => [] as Category[])).find((x) => x.id === category_id);
    const merchant = all && t.merchant_key ? t.merchant_key : null;
    onClose();
    mutate(
      (d) => mapTxns(d, (x) => (x.id === t.id || (merchant && x.merchant_key === merchant) ? (c?.group === "ignore" ? null : { ...x, category_id, category_name: c?.name ?? null, group: c?.group ?? x.group }) : x)),
      async () => {
        await send("PUT", `/transactions/${t.id}/category`, { category_id, remember: false, apply_to_past: false });
        if (merchant) await send("PUT", "/categories/merchant", { merchant_key: merchant, category_id, apply_to_past: true });
      },
    );
  }

  async function ignore() {
    const c = (await loadCategories().catch(() => [] as Category[])).find((x) => x.name === IGNORE_CATEGORY);
    if (c) return setCategory(c.id, false);
    onClose();
    mutate((d) => d, () => Promise.reject(new Error(`no "${IGNORE_CATEGORY}" category`))); // surfaces the failure banner
  }

  const total = t.split_total ?? t.amount;
  const split = t.split != null; // category actions would only move the remainder: split ones edit the parts instead
  const actions: Action[] = [];
  // Moved out of the current cycle into one home can't open yet: undo is the first thing offered.
  if (data.moved_next.transactions.some((x) => x.id === t.id)) actions.push({ icon: <CalendarClock size={18} />, label: "החזר לחודש הזה", run: () => cycle("own")() });
  if (split)
    actions.push(
      { icon: <Split size={18} />, label: "עריכת הפיצול", value: `${t.split!.length} חלקים`, run: () => setMode("split") },
      { icon: <Undo2 size={18} />, label: "ביטול הפיצול", run: () => request((x) => x, () => send("DELETE", `/transactions/${t.id}/split`)) },
    );
  else actions.push({ icon: <Tag size={18} />, label: "שינוי קטגוריה", value: categoryLabel(t.category_name), run: () => setMode({ groups: Object.keys(GROUP_LABEL) as Group[], title: "שינוי קטגוריה", remember: true }) });
  actions.push({ icon: <StickyNote size={18} />, label: t.note ? "עריכת הערה" : "הוספת הערה", tone: "sun", run: () => setMode("note") });
  if (t.review)
    actions.push({
      icon: <Check size={18} />,
      label: "סימון כטופל",
      value: t.review.assignee ? `לבדוק עם ${t.review.assignee}` : "לבדיקה",
      run: () => request((x) => ({ ...x, review: null }), () => send("DELETE", `/transactions/${t.id}/review`)),
    });
  else actions.push({ icon: <MessageCircleQuestion size={18} />, label: other ? `לבדוק עם ${other}` : "לסמן לבדיקה", tone: "sun", run: () => setMode("review") });
  if (!split) actions.push({ icon: <Split size={18} />, label: "פיצול ההוצאה", run: () => setMode("split") });
  if (!split && t.group === "fixed") actions.push({ icon: <Repeat size={18} />, label: "זו לא הוצאה קבועה", run: () => setMode({ groups: ["variable"], title: "לאיזו קטגוריה משתנה?", remember: true }) });
  if (!split && t.group === "variable") actions.push({ icon: <Repeat size={18} />, label: "זו הוצאה קבועה", run: () => setMode({ groups: ["fixed"], title: "לאיזו קטגוריה קבועה?", remember: true }) });
  // The sheet's one primary action (full-width button under the list).
  const primary: Action | null =
    !split && t.group !== "savings" && t.group !== "income" ? { icon: <PiggyBank size={18} />, label: "זו הפקדה לחיסכון", run: () => setMode({ groups: ["savings"], title: "לאיזה חיסכון?", remember: true }) } : null;
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
  if (!split) actions.push({ icon: <EyeOff size={18} />, label: "להוציא מהתזרים", tone: "danger", run: ignore });

  /** Close, apply `optimistic` to this txn, run `req`; the home refetch places it right. */
  function request(optimistic: (x: Txn) => Txn, req: () => Promise<unknown>) {
    onClose();
    mutate((d) => mapTxns(d, (x) => (x.id === t.id ? optimistic(x) : x)), req);
  }

  return (
    <Sheet
      labelledBy="txn-sheet-title"
      onClose={onClose}
      header={
        <>
          <div className="flex items-center gap-2">
            <p className={`chip min-w-0 truncate px-3 py-1.5 text-[13px] ${CHIP[t.group ?? "variable"] ?? "bg-sunken text-text"}`}>
              {t.group ? GROUP_LABEL[t.group] : "לא מסווג"} · {categoryLabel(t.category_name)}
            </p>
            <button type="button" className="icon-btn ms-auto size-11" aria-label="סגירה" onClick={onClose}>
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
          <Money value={Math.abs(total)} className="block text-right text-[46px] leading-none font-extrabold" />
        </>
      }
    >
          {t.note && mode !== "note" && <p className="mb-3 rounded-2xl bg-sun-soft p-3 text-sm whitespace-pre-wrap">{t.note}</p>}
          {t.review && (
            <p className="mb-3 rounded-2xl bg-band-info p-3 text-sm">
              <strong>{t.review.assignee ? `לבדוק עם ${t.review.assignee}` : "לבדיקה"}</strong>
              {t.review.note && ` · ${t.review.note}`}
            </p>
          )}
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
          ) : mode === "review" ? (
            <ReviewForm
              people={people}
              initial={other}
              onCancel={() => setMode(null)}
              onSave={(assignee, note) => request((x) => ({ ...x, review: { assignee, note } }), () => send("PUT", `/transactions/${t.id}/review`, { assignee, note }))}
            />
          ) : mode === "split" ? (
            <SplitForm
              total={total}
              initial={t.split?.map((p) => ({ category_id: p.category_id, amount: String(Math.abs(p.amount)) })) ?? [{ category_id: t.category_id, amount: String(Math.abs(total)) }, { category_id: null, amount: "" }]}
              onCancel={() => setMode(null)}
              onSave={(rows) => request((x) => x, () => send("PUT", `/transactions/${t.id}/split`, splitBody(total, rows)))}
            />
          ) : mode === "fixed" ? (
            <FixedIncomeForm
              day={Number(t.date.slice(8, 10))}
              onCancel={() => setMode(null)}
              onSave={(expected_day, expected_amount) => request((x) => x, () => send("POST", `/transactions/${t.id}/fixed-income`, { expected_day, expected_amount }))}
            />
          ) : mode ? (
            <CategoryForm key={mode.title} {...mode} merchant={t.merchant_key ? t.description : null} current={t.category_id} onCancel={() => setMode(null)} onSave={setCategory} />
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
    </Sheet>
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

function CategoryForm({ groups, title, remember: rememberDefault, merchant, current, onSave, onCancel }: { groups: Group[]; title: string; remember: boolean; merchant: string | null; current: number | null; onSave: (id: number, all: boolean) => void; onCancel: () => void }) {
  const [cat, setCat] = useState<number | null>(null);
  const [remember, setRemember] = useState(rememberDefault);
  return (
    <form
      className="card flex flex-col gap-3 p-3.5"
      onSubmit={(e) => {
        e.preventDefault();
        if (cat != null) onSave(cat, remember && merchant != null);
      }}
    >
      <h3 className="font-bold">{title}</h3>
      <CategorySelect value={cat} onChange={setCat} groups={groups} exclude={current} autoFocus />
      {merchant && (
        <div className="flex flex-col gap-1 rounded-2xl bg-sunken/60 p-3">
          <p className="text-sm font-semibold">להחיל על כל העסקאות של {merchant}?</p>
          <Switch checked={remember} onChange={setRemember} label={remember ? "כן, גם על קודמות ועתידיות" : "רק על העסקה הזו"} />
        </div>
      )}
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

/** Parts editor: category + amount per row; saving needs the parts to add up to the transaction. */
function SplitForm({ total, initial, onSave, onCancel }: { total: number; initial: SplitRow[]; onSave: (rows: SplitRow[]) => void; onCancel: () => void }) {
  const [rows, setRows] = useState(initial);
  const left = splitLeft(total, rows);
  const problem = splitProblem(total, rows);
  // Editing an amount above the last part refills the last part with what's left.
  const set = (i: number, patch: Partial<SplitRow>) =>
    setRows((rs) => {
      const next = rs.map((r, j) => (j === i ? { ...r, ...patch } : r));
      const last = next.length - 1;
      if (patch.amount === undefined || i === last) return next;
      const rest = splitLeft(total, next.slice(0, last));
      return next.map((r, j) => (j === last ? { ...r, amount: rest > 0 ? String(rest) : "" } : r));
    });
  return (
    <form
      className="card flex flex-col gap-3 p-3.5"
      onSubmit={(e) => {
        e.preventDefault();
        if (!problem) onSave(rows);
      }}
    >
      <h3 className="font-bold">פיצול ההוצאה</h3>
      <ul className="flex flex-col gap-3">
        {rows.map((r, i) => (
          <li key={i} className="flex flex-col gap-2 rounded-2xl bg-sunken/60 p-2.5">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-muted">חלק {i + 1}</span>
              <input
                className="input ms-auto max-w-36"
                dir="ltr"
                type="number"
                inputMode="decimal"
                min={0}
                step="0.01"
                value={r.amount}
                onChange={(e) => set(i, { amount: e.target.value })}
                aria-label={`סכום חלק ${i + 1}`}
              />
              {rows.length > 2 && (
                <button type="button" className="icon-btn size-11" aria-label={`הסרת חלק ${i + 1}`} onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}>
                  <Trash2 size={16} />
                </button>
              )}
            </div>
            <CategorySelect value={r.category_id} onChange={(id) => set(i, { category_id: id })} label={`קטגוריה לחלק ${i + 1}`} groups={total > 0 ? ["income", "variable", "fixed", "savings"] : ["variable", "fixed", "savings"]} />
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <button type="button" className="btn-ghost" onClick={() => setRows((rs) => [...rs, { category_id: null, amount: left > 0 ? String(left) : "" }])}>
          <Plus size={16} /> חלק נוסף
        </button>
        {left !== 0 && (
          <span className={left < 0 ? "font-semibold text-danger" : "text-muted"} aria-live="polite">
            {left > 0 ? "נותר לחלק" : "חריגה של"} <Money value={Math.abs(left)} className="font-bold" />
          </span>
        )}
      </div>
      {problem && <p className="text-xs text-muted">{problem}</p>}
      <div className="flex gap-2">
        <button className="btn flex-1" disabled={problem != null}>
          שמירת הפיצול
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel}>
          ביטול
        </button>
      </div>
    </form>
  );
}

/** Who should look at it (when there's more than one person) + an optional question. */
function ReviewForm({ people, initial, onSave, onCancel }: { people: string[]; initial: string | null; onSave: (assignee: string | null, note: string | null) => void; onCancel: () => void }) {
  const [who, setWho] = useState(initial);
  const [note, setNote] = useState("");
  return (
    <form
      className="card flex flex-col gap-3 p-3.5"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(who, note.trim() || null);
      }}
    >
      <h3 className="font-bold">{who ? `לבדוק עם ${who}` : "לסמן לבדיקה"}</h3>
      {people.length > 1 && (
        <div className="flex flex-wrap gap-2" role="group" aria-label="עם מי לבדוק">
          {people.map((p) => (
            <button key={p} type="button" aria-pressed={who === p} className={`chip min-h-11 px-4 text-sm ${who === p ? "bg-brand-fill text-brand-fg" : "bg-sunken text-text"}`} onClick={() => setWho(p)}>
              {p}
            </button>
          ))}
        </div>
      )}
      <textarea className="input min-h-20" value={note} onChange={(e) => setNote(e.target.value)} placeholder="מה לשאול? (לא חובה)" aria-label="הערה לבדיקה" maxLength={500} />
      <p className="text-xs text-muted">תופיע התראה באפליקציה והעסקה תיכנס לרשימת &quot;לבדיקה&quot; בבית.</p>
      <div className="flex gap-2">
        <button className="btn flex-1">שליחה לבדיקה</button>
        <button type="button" className="btn-ghost" onClick={onCancel}>
          ביטול
        </button>
      </div>
    </form>
  );
}
