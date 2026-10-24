"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { Money } from "@/components/Amount";
import { send } from "@/lib/api";
import type { HomeData } from "@/lib/home";
import { useHome } from "./context";
import { Expander } from "./Expander";
import { Illustration } from "./illustrations";

const PILL = "flex w-fit items-center gap-1 rounded-xl border border-border px-3.5 py-2 text-sm font-bold hover:bg-sunken";

/** Current cycle only: this week's allowance, then the month-end goal card (editable). */
export function WeeklySummary({ s }: { s: NonNullable<HomeData["summary"]> }) {
  const over = s.week_left < 0;
  return (
    <>
      <section className="card overflow-hidden">
        <div className="flex flex-col gap-3 p-5">
          <h2 className="text-xl leading-snug font-bold">{over ? "בכמה חרגנו בהוצאות המשתנות השבוע?" : "כמה כסף נשאר להוציא על הוצאות משתנות השבוע?"}</h2>
          <Money value={Math.abs(s.week_left)} className={`self-start text-[44px] leading-none font-light ${over ? "text-danger" : ""}`} />
          <Link href="/balance" className={PILL}>
            ומה מצב העו״ש? <ChevronLeft size={16} aria-hidden />
          </Link>
        </div>
        {s.next_week_allowance ? (
          <div className="border-t border-hairline px-5 py-3 text-sm">
            <p className="font-bold">הוצאות משתנות של שבוע הבא</p>
            <Money value={s.next_week_allowance} />
          </div>
        ) : null}
      </section>
      <GoalCard s={s} />
    </>
  );
}

function GoalCard({ s }: { s: NonNullable<HomeData["summary"]> }) {
  const { mutate } = useHome();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [bad, setBad] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const amount = Number(value);
    if (value.trim() === "" || !Number.isFinite(amount) || amount < 0) return setBad(true);
    setEditing(false);
    setBad(false);
    mutate(
      (d) =>
        d.summary
          ? {
              ...d,
              summary: {
                ...d.summary,
                goal_personal: amount,
                goal: amount + d.summary.goal_plans,
              },
            }
          : d,
      () => send("PUT", "/plan/goal", { amount }),
    );
  }

  return (
    <section id="goal" className="card scroll-mt-20 overflow-hidden">
      <div className="flex flex-col gap-3 p-5">
        <p className="text-sm text-muted">היעד החודשי</p>
        <h2 className="text-xl leading-snug font-bold">כמה אני רוצה להשאיר בצד בסוף החודש?</h2>
        <div className="flex items-end gap-3">
          <div className="flex min-w-0 flex-1 flex-col gap-3">
            {editing ? (
              <form onSubmit={save} className="flex flex-wrap gap-2">
                {s.goal_plans > 0 && (
                  <p className="w-full text-[13px] text-muted">
                    בנוסף ל-
                    <Money value={s.goal_plans} /> של התוכניות
                  </p>
                )}
                <input
                  type="number"
                  required
                  min={0}
                  step="any"
                  inputMode="numeric"
                  dir="ltr"
                  className="input min-h-11 max-w-36 flex-1"
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  aria-label="יעד אישי לסוף החודש"
                  autoFocus
                  onFocus={(e) => e.target.select()}
                />
                <button className="btn min-h-11">שמירה</button>
                <button type="button" className="btn-ghost" onClick={() => setEditing(false)}>
                  ביטול
                </button>
              </form>
            ) : (
              <>
                <Money value={s.goal} className="self-start text-3xl font-bold text-sun-strong" />
                {s.goal_plans > 0 && (
                  <p className="-mt-2 text-xs text-muted">
                    אישי <Money value={s.goal_personal} /> + תוכניות <Money value={s.goal_plans} />
                  </p>
                )}
                <button
                  type="button"
                  className="btn flex w-fit min-h-10 items-center gap-1 px-4"
                  onClick={() => {
                    setValue(String(s.goal_personal));
                    setEditing(true);
                  }}
                >
                  בחירת יעד <ChevronLeft size={16} aria-hidden />
                </button>
              </>
            )}
            {bad && (
              <p className="text-sm font-semibold text-danger" role="alert">
                יש להזין סכום חיובי.
              </p>
            )}
          </div>
          <div className="w-28 shrink-0">
            <Illustration name="coin" active />
          </div>
        </div>
      </div>
      <Expander className="border-t border-hairline px-3" buttonClassName="flex min-h-12 px-2" label={<span className="text-sm font-bold">לתכנן קדימה</span>}>
        <div className="flex flex-col gap-2 px-2 pb-4 text-sm">
          <p className="text-muted">התוכניות הגדולות עוזרות להבין כמה לשים בצד כל חודש כדי להגשים אותן, ולעקוב אחרי ההתקדמות בקלות.</p>
          <Link href="/plans" className="link flex items-center gap-1 font-bold">
            {s.goal_plans > 0 ? "לתוכניות הגדולות" : "להוספת תוכניות גדולות"} <ChevronLeft size={16} aria-hidden />
          </Link>
        </div>
      </Expander>
    </section>
  );
}
