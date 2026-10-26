"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Status } from "@/components/Card";
import { ApiError, send, type Settings } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export type Patch = (p: Partial<Settings>) => Promise<boolean>;

export const hh = (h: number) => `${String(h).padStart(2, "0")}:00`;
export const range = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => from + i);

/** A settings sub-page's header: back to the settings menu, then the title. */
export function SubHeader({ title }: { title: string }) {
  return (
    <div className="flex items-center gap-2">
      <Link href="/settings" className="icon-btn size-10" aria-label="חזרה להגדרות">
        <ArrowRight size={20} />
      </Link>
      <h1 className="page-title">{title}</h1>
    </div>
  );
}

/** A settings sub-page that edits /settings: loads it, hands children the data and a `patch` that saves and shows the toast. */
export function SettingsScreen({ title, children }: { title: string; children: (s: Settings, patch: Patch, flash: (text: string) => void) => React.ReactNode }) {
  const { data, setData, error } = useApi<Settings>("/settings");
  const [msg, setMsg] = useState<{ text: string; bad?: boolean; n: number } | null>(null);
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(null), 2200);
    return () => clearTimeout(t);
  }, [msg]);
  const flash = (text: string, bad?: boolean) => setMsg((m) => ({ text, bad, n: (m?.n ?? 0) + 1 }));

  const patch: Patch = async (p) => {
    try {
      const next = await send<Settings>("PUT", "/settings", p);
      setData(() => next);
      flash("השינוי נשמר");
      return true;
    } catch (err) {
      flash(err instanceof ApiError && err.status === 422 ? "הערך לא תקין, השינוי לא נשמר" : "השמירה נכשלה, נסו שוב", true);
      return false;
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <SubHeader title={title} />
      <Status loading={!data} error={error} />
      {data && children(data, patch, flash)}
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

/** A card of rows. On a sub-page the page title names it, so `title` is optional; `hint` and `action` sit at its top. */
export function Section({ id, title, hint, action, children }: { id: string; title?: string; hint?: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={title && `${id}-h`} className="card flex flex-col gap-1 p-4 sm:p-5">
      {(title || hint || action) && (
        <div className="mb-2 flex items-start gap-2">
          <div className="flex-1">
            {title && <h2 id={`${id}-h`} className="section-title">{title}</h2>}
            {hint && <p className={`text-sm text-muted ${title ? "mt-0.5" : ""}`}>{hint}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-hairline py-3 first-of-type:border-t-0">
      <div className="min-w-48 flex-1">
        <p className="font-semibold">{label}</p>
        {hint && <p className="text-[13px] text-muted">{hint}</p>}
      </div>
      {children}
    </div>
  );
}

/** Saves on blur / Enter, only when the value changed. */
export function NumberField({ label, value, onSave }: { label: string; value: number; onSave: (v: number) => Promise<boolean> }) {
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
