"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bell, CalendarRange, ChevronLeft, GripVertical, KeyRound, Palette, RefreshCw, Send, Tags, Wallet, type LucideIcon } from "lucide-react";
import { Status } from "@/components/Card";
import { Select } from "@/components/ui/Select";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ApiError, send, type Settings } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Row, Section, type Patch } from "./parts";
import { TelegramCard } from "./TelegramCard";

const SECTIONS: { id: string; label: string; icon: LucideIcon }[] = [
  { id: "cycle", label: "החודש שלי", icon: CalendarRange },
  { id: "sync", label: "סנכרון אוטומטי", icon: RefreshCw },
  { id: "alerts", label: "התראות", icon: Bell },
  { id: "telegram", label: "טלגרם", icon: Send },
  { id: "display", label: "תצוגה", icon: Palette },
  { id: "data", label: "חשבונות ונתונים", icon: Wallet },
];

const hh = (h: number) => `${String(h).padStart(2, "0")}:00`;
const range = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => from + i);

export default function SettingsPage() {
  const { data, setData, error } = useApi<Settings>("/settings");
  const [msg, setMsg] = useState<{ text: string; bad?: boolean; n: number } | null>(null);
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(null), 2200);
    return () => clearTimeout(t);
  }, [msg]);

  const patch: Patch = async (p) => {
    try {
      const next = await send<Settings>("PUT", "/settings", p);
      setData(() => next);
      setMsg((m) => ({ text: "השינוי נשמר", n: (m?.n ?? 0) + 1 }));
      return true;
    } catch (err) {
      setMsg((m) => ({ text: err instanceof ApiError && err.status === 422 ? "הערך לא תקין, השינוי לא נשמר" : "השמירה נכשלה, נסו שוב", bad: true, n: (m?.n ?? 0) + 1 }));
      return false;
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <h1 className="page-title">הגדרות</h1>
      <Status loading={!data} error={error} />
      {data && (
        <div className="grid gap-5 lg:grid-cols-[13rem_1fr] lg:items-start">
          <nav aria-label="חלקי ההגדרות" className="hidden lg:sticky lg:top-24 lg:block">
            <ul className="flex flex-col gap-0.5">
              {SECTIONS.map(({ id, label, icon: Icon }) => (
                <li key={id}>
                  <a href={`#${id}`} className="flex min-h-10 items-center gap-2.5 rounded-xl px-3 text-sm font-semibold text-muted hover:bg-sunken hover:text-text">
                    <Icon size={17} strokeWidth={1.8} /> {label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <div className="flex min-w-0 flex-col gap-4">
            <Section id="cycle" title="החודש שלי" hint="איך FreeRise מחלק את הזמן לחודשים ומה נחשב חודש טוב.">
              <Row label="יום תחילת החודש" hint="התזרים, התקציב והתחזית נספרים מהיום הזה. כדאי לבחור את יום המשכורת.">
                <Select label="יום תחילת החודש" className="w-28" value={String(data.cycle_start_day)} onChange={(v) => patch({ cycle_start_day: Number(v) })} options={range(1, 28).map((d) => ({ value: String(d), label: `${d} בחודש` }))} />
              </Row>
              <Row label="יעד לסוף החודש" hint="כמה תרצו שיישאר בסוף כל חודש. אפשר לשנות לכל חודש בנפרד במסך התזרים.">
                <NumberField label="יעד לסוף החודש" value={data.month_end_goal_default} onSave={(v) => patch({ month_end_goal_default: v })} />
              </Row>
              <Row label="גמישות במועד המשכורת" hint="הכנסה קבועה שמגיעה עד כמה ימים לפני או אחרי מועדה עדיין נספרת לחודש שלה.">
                <Select label="גמישות במועד המשכורת" className="w-28" value={String(data.income_grace_days)} onChange={(v) => patch({ income_grace_days: Number(v) })} options={range(0, 15).map((d) => ({ value: String(d), label: d === 0 ? "בלי" : `${d} ימים` }))} />
              </Row>
            </Section>

            <Section id="sync" title="סנכרון אוטומטי" hint="בשעות המסומנות FreeRise מושך תנועות חדשות מכל החיבורים.">
              <SyncHours hours={data.sync_hours} onChange={(sync_hours) => patch({ sync_hours })} />
            </Section>

            <Section id="alerts" title="התראות" hint="ההתראות מופיעות בפעמון למעלה, ואפשר לקבל אותן גם בטלגרם.">
              <Row label="בדיקה יומית" hint="שעה שבה נבדקות התראות כמו חריגה מתקציב ותזכורות. נבדקות גם אחרי כל סנכרון.">
                <Select label="שעת הבדיקה היומית" className="w-28" value={String(data.digest_hour)} onChange={(v) => patch({ digest_hour: Number(v) })} options={range(0, 23).map((h) => ({ value: String(h), label: hh(h) }))} />
              </Row>
              <Row label="עסקה גדולה מעל" hint="התראה על חיוב בודד מעל הסכום הזה, או מעל פי 3 מהרגיל בקטגוריה שלו, הגבוה מביניהם.">
                <NumberField label="סף לעסקה גדולה" value={data.large_txn_min} onSave={(v) => patch({ large_txn_min: v })} />
              </Row>
            </Section>

            <TelegramCard settings={data} patch={patch} />

            <Section id="display" title="תצוגה">
              <ThemeToggle />
            </Section>

            <Section id="data" title="חשבונות ונתונים">
              <nav className="-my-1 flex flex-col">
                <NavRow href="/settings/credentials" icon={KeyRound} label="חיבורים לבנקים ואשראי" />
                <NavRow href="/accounts" icon={Wallet} label="חשבונות וכרטיסים" />
                <NavRow href="/home?categorize=1" icon={Tags} label="סיווג עסקאות" />
                <NavRow href="/settings/categories" icon={GripVertical} label="סדר הקטגוריות בבית" />
              </nav>
            </Section>
          </div>
        </div>
      )}
      {msg && (
        <p
          key={msg.n}
          role="status"
          className={`fixed z-50 inset-x-0 bottom-24 mx-auto w-fit rounded-full px-4 py-2 text-sm font-bold shadow-nav lg:bottom-8 ${msg.bad ? "bg-danger-soft text-danger-strong" : "bg-brand-fill text-brand-fg"}`}
        >
          {msg.text}
        </p>
      )}
    </div>
  );
}

/** Saves on blur / Enter, only when the value changed. */
function NumberField({ label, value, onSave }: { label: string; value: number; onSave: (v: number) => Promise<boolean> }) {
  const [text, setText] = useState(String(value));
  const commit = async () => {
    const v = Number(text);
    if (text.trim() === "" || !Number.isFinite(v) || v < 0) return setText(String(value));
    if (v !== value && !(await onSave(v))) setText(String(value));
  };
  return (
    <div className="relative w-36">
      <input
        aria-label={label}
        type="number"
        min={0}
        step="any"
        dir="ltr"
        inputMode="decimal"
        className="input pl-8"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
      />
      <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-faint">₪</span>
    </div>
  );
}

const PRESETS: { label: string; hours: number[] }[] = [
  { label: "3 פעמים ביום", hours: [7, 14, 21] },
  { label: "פעם ביום", hours: [7] },
  { label: "ידני בלבד", hours: [] },
];

function SyncHours({ hours, onChange }: { hours: number[]; onChange: (h: number[]) => void }) {
  const toggle = (h: number) => onChange(hours.includes(h) ? hours.filter((x) => x !== h) : [...hours, h].sort((a, b) => a - b));
  const same = (a: number[]) => a.length === hours.length && a.every((h, i) => h === hours[i]);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button key={p.label} type="button" aria-pressed={same(p.hours)} onClick={() => onChange(p.hours)} className={`chip min-h-9 px-3.5 text-sm ${same(p.hours) ? "bg-brand-fill text-brand-fg" : "bg-sunken text-text"}`}>
            {p.label}
          </button>
        ))}
      </div>
      <div role="group" aria-label="שעות סנכרון" className="grid grid-cols-6 gap-1.5 sm:grid-cols-8 lg:grid-cols-12" dir="ltr">
        {range(0, 23).map((h) => {
          const on = hours.includes(h);
          return (
            <button key={h} type="button" aria-pressed={on} aria-label={`סנכרון בשעה ${hh(h)}`} onClick={() => toggle(h)} className={`min-h-10 rounded-[10px] text-[13px] font-bold tabular-nums ${on ? "bg-brand-fill text-brand-fg" : "bg-sunken text-muted hover:text-text"}`}>
              {hh(h)}
            </button>
          );
        })}
      </div>
      <p className="text-[13px] text-muted">
        {hours.length === 0
          ? "אין סנכרון אוטומטי. אפשר לסנכרן ידנית ממסך החיבורים."
          : `${hours.length === 1 ? "סנכרון אחד" : `${hours.length} סנכרונים`} ביום. בנקים מסוימים חוסמים כניסות תכופות, אז עדיף לא יותר מ-4.`}
      </p>
    </div>
  );
}

function NavRow({ href, icon: Icon, label }: { href: string; icon: LucideIcon; label: string }) {
  return (
    <Link href={href} className="flex min-h-12 items-center gap-3 border-t border-hairline font-semibold first:border-t-0">
      <Icon size={18} strokeWidth={1.8} className="text-muted" />
      <span className="flex-1">{label}</span>
      <ChevronLeft size={18} className="text-faint" />
    </Link>
  );
}
