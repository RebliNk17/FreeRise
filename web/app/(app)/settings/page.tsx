"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bell, CalendarRange, ChevronLeft, GripVertical, Moon, Palette, RefreshCw, Send, Sun, Tags, Wallet, type LucideIcon } from "lucide-react";
import { Status } from "@/components/Card";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/Switch";
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
  const { data: health } = useApi<{ version: string }>("/health");
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

            <Section id="sync" title="סנכרון אוטומטי" action={<SyncSwitch hours={data.sync_hours} patch={patch} />} hint="בשעות המסומנות FreeRise מושך תנועות חדשות מכל החיבורים.">
              <SyncTimeline hours={data.sync_hours} onChange={(sync_hours) => patch({ sync_hours })} />
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
                <NavRow href="/accounts" icon={Wallet} label="חשבונות וחיבורים" />
                <NavRow href="/home?categorize=1" icon={Tags} label="סיווג עסקאות" />
                <NavRow href="/settings/categories" icon={GripVertical} label="סדר הקטגוריות בבית" />
              </nav>
            </Section>

            {health && <p dir="ltr" className="text-center text-xs text-faint tabular-nums">FreeRise v{health.version}</p>}
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

const DEFAULT_SYNC = [7, 14, 21];

/** Off = no hours (manual sync only). On restores the default; ponytail: remember the last custom hours if turning it back on loses them too often. */
function SyncSwitch({ hours, patch }: { hours: number[]; patch: Patch }) {
  return <Switch label={hours.length ? "פעיל" : "כבוי"} checked={hours.length > 0} onChange={(on) => patch({ sync_hours: on ? DEFAULT_SYNC : [] })} />;
}

function SyncSummary({ hours }: { hours: number[] }) {
  if (!hours.length) return <p className="text-[13px] text-muted">אין סנכרון אוטומטי. אפשר לסנכרן ידנית ממסך החיבורים.</p>;
  const now = new Date().getHours();
  const next = hours.find((h) => h > now) ?? hours[0];
  return (
    <p className="text-[13px] text-muted">
      {hours.length === 1 ? "סנכרון אחד" : `${hours.length} סנכרונים`} ביום · הבא ב-<span className="font-bold text-text tabular-nums">{hh(next)}</span>
      {hours.length > 4 && <span className="text-sun-strong"> · בנקים מסוימים חוסמים כניסות תכופות, עדיף לא יותר מ-4</span>}
    </p>
  );
}

/** The day as one strip (two rows of 12 on phones, so each hour is tappable); night hours shaded, picked hours filled and labelled. */
function SyncTimeline({ hours, onChange }: { hours: number[]; onChange: (h: number[]) => void }) {
  const toggle = (h: number) => onChange(hours.includes(h) ? hours.filter((x) => x !== h) : [...hours, h].sort((a, b) => a - b));
  if (!hours.length) return <SyncSummary hours={hours} />;
  return (
    <div className="flex flex-col gap-4">
      <div dir="ltr">
        <div className="relative hidden h-6 text-[13px] font-bold text-brand tabular-nums sm:block">
          {hours.map((h) => (
            <span key={h} className="absolute -translate-x-1/2" style={{ left: `${((h + 0.5) / 24) * 100}%` }}>
              {hh(h)}
            </span>
          ))}
        </div>
        <div role="group" aria-label="שעות סנכרון" className="grid grid-cols-12 gap-x-0.5 gap-y-1.5 sm:grid-cols-24">
          {range(0, 23).map((h) => {
            const on = hours.includes(h);
            const ends = h === 0 ? "rounded-l-xl" : h === 23 ? "rounded-r-xl" : h === 11 ? "max-sm:rounded-r-xl" : h === 12 ? "max-sm:rounded-l-xl" : "";
            return (
              <button
                key={h}
                type="button"
                data-tip={hh(h)}
                aria-pressed={on}
                aria-label={`סנכרון בשעה ${hh(h)}`}
                onClick={() => toggle(h)}
                className={`h-11 min-w-0 rounded-[4px] sm:h-12 ${ends} ${on ? "bg-brand-fill" : `${h < 6 || h >= 22 ? "bg-border" : "bg-sunken"} hover:bg-brand-soft`}`}
              >
                <span aria-hidden className={`text-xs font-bold tabular-nums sm:hidden ${on ? "text-brand-fg" : "text-muted"}`}>
                  {String(h).padStart(2, "0")}
                </span>
              </button>
            );
          })}
        </div>
        <div className="mt-1.5 hidden justify-between text-xs text-faint tabular-nums sm:flex">
          <span className="flex items-center gap-1"><Moon size={12} aria-hidden /> 00:00</span>
          <span>06:00</span>
          <span className="flex items-center gap-1"><Sun size={12} aria-hidden /> 12:00</span>
          <span>18:00</span>
          <span>24:00</span>
        </div>
      </div>
      <SyncSummary hours={hours} />
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
