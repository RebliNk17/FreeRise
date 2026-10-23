"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { Card, Status } from "@/components/Card";
import { ApiError, send, type Settings } from "@/lib/api";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useApi } from "@/lib/useApi";

export default function SettingsPage() {
  const { data, error } = useApi<Settings>("/settings");
  return (
    <div className="flex flex-col gap-4">
      <h1 className="page-title">הגדרות</h1>
      <Status loading={!data} error={error} />
      {data && <SettingsForm initial={data} />}
      <Card>
        <h2 className="section-title">תצוגה</h2>
        <ThemeToggle />
      </Card>
      <Card>
        <Link href="/settings/credentials" className="flex min-h-11 items-center justify-between font-semibold">
          חיבורים <ChevronLeft size={18} className="text-faint" />
        </Link>
        <Link href="/accounts" className="flex min-h-11 items-center justify-between border-t border-hairline pt-3 font-semibold">
          חשבונות <ChevronLeft size={18} className="text-faint" />
        </Link>
        <Link href="/settings/categories" className="flex min-h-11 items-center justify-between border-t border-hairline pt-3 font-semibold">
          סדר הקטגוריות בבית <ChevronLeft size={18} className="text-faint" />
        </Link>
      </Card>
    </div>
  );
}

function SettingsForm({ initial }: { initial: Settings }) {
  const [day, setDay] = useState(String(initial.cycle_start_day));
  const [goal, setGoal] = useState(String(initial.month_end_goal_default));
  const [msg, setMsg] = useState("");

  async function save(e: React.FormEvent) {
    e.preventDefault();
    try {
      await send("PUT", "/settings", { cycle_start_day: Number(day), month_end_goal_default: Number(goal) });
      setMsg("נשמר.");
    } catch (err) {
      setMsg(err instanceof ApiError && err.status === 422 ? "יום תחילת החודש חייב להיות בין 1 ל-28." : "השמירה נכשלה.");
    }
  }

  return (
    <form onSubmit={save} className="card flex flex-col gap-3 p-4">
      <label className="flex flex-col gap-1.5 text-[13px] text-muted">
        יום תחילת החודש התזרימי
        <input type="number" min={1} max={28} required dir="ltr" inputMode="numeric" className="input" value={day} onChange={(e) => setDay(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1.5 text-[13px] text-muted">
        יעד ברירת מחדל לסוף החודש
        <input type="number" min={0} step="any" required dir="ltr" inputMode="numeric" className="input" value={goal} onChange={(e) => setGoal(e.target.value)} />
      </label>
      {msg && <p className="text-sm text-muted" role="status">{msg}</p>}
      <button className="btn self-start">שמירה</button>
    </form>
  );
}
