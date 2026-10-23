"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus } from "lucide-react";
import { Amount } from "@/components/Amount";
import { Switch } from "@/components/Switch";
import { EmptyState } from "@/components/Card";
import { useInactive } from "@/components/InactiveFilter";
import { ProviderLogo } from "@/components/ProviderLogo";
import { api, send, type Account } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { providerName } from "@/lib/providers";
import { DataHealth } from "./DataHealth";

const KIND: Record<Account["kind"], string> = { bank: "בנק", card: "כרטיס אשראי", fund: "קרן" };

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const { shown, toggle: inactiveToggle } = useInactive(accounts);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Account[]>("/accounts")
      .then(setAccounts)
      .catch(() => setError("טעינת החשבונות נכשלה."));
  }, []);

  async function toggle(a: Account, excluded: boolean) {
    setAccounts((as) => as?.map((x) => (x.id === a.id ? { ...x, excluded } : x)) ?? null);
    try {
      await send("PATCH", `/accounts/${a.id}`, { excluded });
    } catch {
      setAccounts((as) => as?.map((x) => (x.id === a.id ? { ...x, excluded: a.excluded } : x)) ?? null);
      setError("העדכון נכשל.");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="page-title">חשבונות</h1>
      {error && <p className="rounded-2xl bg-danger-soft px-4 py-3 text-sm font-semibold text-danger-strong" role="alert">{error}</p>}
      {accounts === null && !error && <p className="text-muted">טוען…</p>}
      {accounts?.length === 0 && (
        <EmptyState text="אין חשבונות עדיין. הוסיפו פרטי התחברות בהגדרות וסנכרנו.">
          <Link href="/settings/credentials?add=1" className="btn">
            <Plus size={18} /> הוספת חיבור
          </Link>
        </EmptyState>
      )}
      <ul className="flex flex-col gap-3">
        {shown?.map((a) => (
          <li key={a.id} className={`card flex flex-col gap-3 p-3.5 ${a.excluded ? "opacity-60" : ""}`}>
            <div className="flex items-start gap-3">
              <span className="size-11 shrink-0">
                <ProviderLogo provider={a.provider} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate font-bold">{a.label}</div>
                <div className="text-xs text-muted">
                  {providerName(a.provider)} · {KIND[a.kind] ?? a.kind}
                </div>
              </div>
              <div className="text-end">
                {a.balance != null ? <Amount value={a.balance} className="text-lg font-bold" /> : <span className="text-muted">—</span>}
                {a.balance_as_of && (
                  <div className="text-xs text-muted">
                    נכון ל-<span dir="ltr">{formatDate(a.balance_as_of)}</span>
                  </div>
                )}
              </div>
            </div>
            <HolderField a={a} onSaved={(holder) => setAccounts((as) => as?.map((x) => (x.id === a.id ? { ...x, holder } : x)) ?? null)} onError={() => setError("העדכון נכשל.")} />
            <Switch checked={a.excluded} onChange={(v) => toggle(a, v)} label="החרגה מתזרים המזומנים" />
          </li>
        ))}
      </ul>
      {inactiveToggle}
      {accounts && accounts.length > 0 && <DataHealth />}
    </div>
  );
}

/** "על שם": whose card it is; saved on blur, empty = the login's owner. */
function HolderField({ a, onSaved, onError }: { a: Account; onSaved: (holder: string) => void; onError: () => void }) {
  const [value, setValue] = useState(a.holder);
  async function save() {
    if (value.trim() === a.holder) return;
    try {
      const saved = (await send<Account>("PATCH", `/accounts/${a.id}`, { holder: value.trim() })).holder;
      setValue(saved); // empty -> the login's owner
      onSaved(saved);
    } catch {
      setValue(a.holder);
      onError();
    }
  }
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="shrink-0 text-muted">על שם</span>
      <input className="input min-h-10 flex-1 py-1.5" value={value} maxLength={100} onChange={(e) => setValue(e.target.value)} onBlur={save} onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()} />
    </label>
  );
}
