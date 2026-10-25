"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { X } from "lucide-react";
import { api, type Credential } from "@/lib/api";
import { providerName } from "@/lib/providers";

/** "מקס של שי כהן": the connection as the toasts name it. */
export const syncName = (c: Pick<Credential, "provider" | "owner" | "label">) => `${providerName(c.provider)} של ${c.owner || c.label}`;

type Watch = { id: number; name: string };
export type RunRef = { credential_id: number; run_id: number; already_running: boolean };
type Run = { id: number; status: string; added: number };
type Toast = { key: number; text: string; failed?: boolean };

const EVENT = "freerise:sync";
const STORE = "freerise:sync-watch";
const FINISHED = ["success", "failed", "otp_timeout"];

/** A page asked for syncs: show "started" now and "done" when each finishes, on whatever page you are. */
export function announceSync(runs: RunRef[], creds: Pick<Credential, "id" | "provider" | "owner" | "label">[]) {
  const named = runs.flatMap((r) => {
    const c = creds.find((x) => x.id === r.credential_id);
    return c ? [{ id: r.run_id, name: syncName(c), already: r.already_running }] : [];
  });
  window.dispatchEvent(new CustomEvent(EVENT, { detail: named }));
}

function load(): Watch[] {
  try {
    return JSON.parse(sessionStorage.getItem(STORE) ?? "[]");
  } catch {
    return [];
  }
}

/** Bottom toasts for manual syncs; polls the runs only while one it announced is still going. */
export function SyncToasts() {
  const [watch, setWatch] = useState<Watch[]>(load);
  const [toasts, setToasts] = useState<Toast[]>([]);

  function push(text: string, failed = false) {
    const key = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-2), { key, text, failed }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.key !== key)), failed ? 12_000 : 7_000);
  }

  useEffect(() => {
    try {
      sessionStorage.setItem(STORE, JSON.stringify(watch));
    } catch {}
  }, [watch]);

  useEffect(() => {
    const on = (e: Event) => {
      const runs = (e as CustomEvent<(Watch & { already: boolean })[]>).detail;
      if (!runs.length) return push("אין חיבורים פעילים לסנכרון.");
      if (runs.length === 1) push(runs[0].already ? `${runs[0].name} כבר מסתנכרן. נעדכן כשזה יסתיים.` : `מסנכרנים את ${runs[0].name}. נעדכן כשזה יסתיים.`);
      else push(`מסנכרנים ${runs.length} חיבורים. נעדכן כשכל אחד יסתיים.`);
      setWatch((w) => [...w.filter((x) => !runs.some((r) => r.id === x.id)), ...runs.map(({ id, name }) => ({ id, name }))]);
    };
    window.addEventListener(EVENT, on);
    return () => window.removeEventListener(EVENT, on);
  }, []);

  useEffect(() => {
    if (!watch.length) return;
    const poll = () => {
      if (document.hidden) return;
      api<Run[]>("/sync/runs?limit=50")
        .then((runs) => {
          const done = watch.filter((w) => {
            const r = runs.find((x) => x.id === w.id);
            if (!r) return true; // gone (connection deleted) or too old to list
            if (!FINISHED.includes(r.status)) return false;
            if (r.status === "success") push(`הסנכרון של ${w.name} הסתיים · ${r.added ? `${r.added} תנועות חדשות` : "אין תנועות חדשות"}`);
            else push(`הסנכרון של ${w.name} נכשל.`, true);
            return true;
          });
          if (done.length) setWatch((ws) => ws.filter((w) => !done.includes(w)));
        })
        .catch(() => {});
    };
    poll();
    const t = setInterval(poll, 4000);
    document.addEventListener("visibilitychange", poll); // back on the tab: report right away
    return () => {
      clearInterval(t);
      document.removeEventListener("visibilitychange", poll);
    };
  }, [watch]);

  return (
    <div className="pointer-events-none fixed inset-x-4 bottom-[calc(max(1rem,env(safe-area-inset-bottom))+4.75rem)] z-30 mx-auto flex max-w-md flex-col gap-2 md:bottom-4" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.key} className={`pointer-events-auto flex items-center gap-2 rounded-2xl px-4 py-3 text-sm shadow-nav ${t.failed ? "bg-danger-soft text-danger-strong" : "bg-text text-bg"}`}>
          <span className="min-w-0 flex-1">{t.text}</span>
          {t.failed && (
            <Link href="/settings/credentials" className="shrink-0 font-bold underline">
              לפרטים
            </Link>
          )}
          <button type="button" className="-me-1 flex size-8 shrink-0 items-center justify-center rounded-lg opacity-70 hover:opacity-100" aria-label="סגירה" onClick={() => setToasts((x) => x.filter((y) => y.key !== t.key))}>
            <X size={16} />
          </button>
        </div>
      ))}
    </div>
  );
}
