"use client";

import { useState } from "react";
import Link from "next/link";
import { Pencil } from "lucide-react";
import { Money } from "@/components/Amount";
import { SunHorizon } from "@/components/Logo";
import { send } from "@/lib/api";
import type { HomeData } from "@/lib/home";
import { useHome } from "./context";

/** Current cycle only: this week's allowance, next week, and the month-end goal (editable). */
export function WeeklySummary({ s }: { s: NonNullable<HomeData["summary"]> }) {
  const { mutate } = useHome();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [bad, setBad] = useState(false);
  const over = s.week_left < 0;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const amount = Number(value);
    if (value.trim() === "" || !Number.isFinite(amount) || amount < 0) return setBad(true);
    setEditing(false);
    setBad(false);
    mutate(
      (d) => (d.summary ? { ...d, summary: { ...d.summary, goal_personal: amount, goal: amount + d.summary.goal_plans } } : d),
      () => send("PUT", "/plan/goal", { amount }),
    );
  }

  return (
    <section id="goal" className="relative scroll-mt-20 overflow-hidden rounded-3xl bg-brand-fill p-5 text-brand-fg">
      <SunHorizon width={190} ground="var(--brand-fill)" line="rgb(234 246 241 / 0.6)" className="pointer-events-none absolute -bottom-3.5 -left-5 opacity-90" />
      <div className="relative">
        <p className={`text-sm ${over ? "font-semibold text-on-fill-danger" : "text-on-fill-muted"}`}>{over ? "חריגה השבוע" : "נשאר להוציא השבוע"}</p>
        <Money value={Math.abs(s.week_left)} className={`mt-1 block text-right text-[44px] leading-[1.1] font-extrabold ${over ? "text-on-fill-danger" : ""}`} />
        {editing ? (
          <form onSubmit={save} className="mt-3.5 flex flex-wrap gap-2">
            <p className="w-full text-[13px] text-white">
              {s.goal_plans > 0 ? (
                <>
                  כמה להשאיר בצד <b>בנוסף</b> ל-<Money value={s.goal_plans} /> של התוכניות?
                </>
              ) : (
                "כמה להשאיר בצד בסוף החודש?"
              )}
            </p>
            <input type="number" required min={0} step="any" inputMode="numeric" dir="ltr" className="input min-h-11 max-w-40 flex-1" value={value} onChange={(e) => setValue(e.target.value)} aria-label="יעד אישי לסוף החודש" autoFocus onFocus={(e) => e.target.select()} />
            <button className="btn-accent min-h-11 rounded-[14px]">שמירה</button>
            <button type="button" className="btn-ghost bg-white/12 text-brand-fg" onClick={() => setEditing(false)}>
              ביטול
            </button>
            {s.goal_plans > 0 && (
              <p className="w-full text-xs text-white/85">
                סה״כ יעד לסוף החודש: <Money value={(Number(value) || 0) + s.goal_plans} className="font-bold" />
              </p>
            )}
          </form>
        ) : (
          <div className="mt-3.5 flex flex-wrap items-center gap-2 text-[13px]">
            {over && <span className="chip bg-danger text-white">חריגה</span>}
            {s.next_week_allowance ? (
              <span className="rounded-full bg-white/12 px-3 py-1.5">
                בשבוע הבא <Money value={s.next_week_allowance} className="font-bold" />
              </span>
            ) : null}
            <button
              type="button"
              className="flex items-center gap-1.5 rounded-full bg-sun/22 px-3 py-1.5 text-on-fill-sun hover:bg-sun/30"
              aria-label="עריכת היעד"
              onClick={() => {
                setValue(String(s.goal_personal));
                setEditing(true);
              }}
            >
              יעד לסוף החודש <Money value={s.goal} className="font-bold" />
              <Pencil size={13} aria-hidden />
            </button>
          </div>
        )}
        {s.goal_plans > 0 && !editing && (
          <p className="relative z-10 mt-2 w-fit rounded-full bg-white/12 px-3 py-1 text-xs font-medium text-white">
            אישי <Money value={s.goal_personal} /> +{" "}
            <Link href="/plans" className="underline">
              תוכניות <Money value={s.goal_plans} />
            </Link>
          </p>
        )}
        {bad && <p className="mt-2 text-sm font-semibold text-on-fill-danger" role="alert">יש להזין סכום חיובי.</p>}
      </div>
    </section>
  );
}
