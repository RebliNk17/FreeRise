"use client";

import Link from "next/link";
import { ArrowRight, CreditCard, Landmark } from "lucide-react";
import { Money } from "@/components/Amount";
import { Status } from "@/components/Card";
import type { Plan } from "@/lib/api";
import { formatDate, formatTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useHiddenAccounts, withHidden } from "@/lib/viewFilter";

type Acct = Plan["balances"]["accounts"][number];

/** "מצב העו״ש" (from the home's "ומה מצב העו״ש?"): a card per bank account, then each card's upcoming charge. */
export default function BalancePage() {
  const { data, error } = useApi<Plan>(withHidden("/plan/current", useHiddenAccounts()));
  const b = data?.balances;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <Link href="/home" className="icon-btn size-10" aria-label="חזרה לבית">
          <ArrowRight size={20} />
        </Link>
        <h1 className="page-title">מצב העו״ש</h1>
      </div>
      <Status loading={!data} error={error} />
      {b && (
        <>
          <SectionLabel icon={<Landmark size={13} aria-hidden />} label="יתרת העו״ש" tone="bg-positive-fill" line="bg-positive-fill" />
          {b.accounts.map((a) => (
            <AccountCard key={a.id} a={a} amount={a.balance} tone={a.balance < 0 ? "text-danger" : "text-positive"} number={a.number} />
          ))}
          <SectionLabel icon={<CreditCard size={13} aria-hidden />} label="חיובי האשראי" tone="bg-danger" line="bg-danger" />
          <p className="-mt-2 text-sm">
            סה״כ חיובים עתידיים: <Money value={b.upcoming_card_charges} className="font-bold" />
          </p>
          {b.cards
            .filter((c) => c.balance !== 0)
            .sort((x, y) => y.balance - x.balance)
            .map((c) => (
              <AccountCard key={c.id} a={c} amount={-c.balance} tone="text-danger" number={`**** ${c.number}`} card />
            ))}
          {data.fees.total > 0 && (
            <p className="flex items-baseline px-1 text-sm text-muted">
              <span className="flex-1">עמלות החודש</span>
              <Money value={data.fees.total} />
            </p>
          )}
          <p className="px-1 text-xs text-muted">החיוב הקרוב בכל כרטיס הוא היתרה שחברת האשראי מדווחת; כשאין כזו, החיובים שנצברו בכרטיס במחזור הנוכחי.</p>
        </>
      )}
    </div>
  );
}

function SectionLabel({ icon, label, tone, line }: { icon: React.ReactNode; label: string; tone: string; line: string }) {
  return (
    <div className="mt-2 flex items-center">
      <span className={`flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-bold text-white ${tone}`}>
        {icon}
        {label}
      </span>
      <span className={`h-px flex-1 ${line}`} aria-hidden />
    </div>
  );
}

/** card: a card's as_of is the provider's billing date, not when it synced. */
function AccountCard({ a, amount, tone, number, card = false }: { a: Acct; amount: number; tone: string; number: string; card?: boolean }) {
  return (
    <section className="card overflow-hidden" aria-label={a.display_name}>
      <div className="flex flex-col p-5">
        {a.as_of && (
          <p className="text-xs text-muted">
            {card ? (
              <>
                לחיוב ב-<span dir="ltr">{formatDate(a.as_of)}</span>
              </>
            ) : (
              <>
                מעודכן ל-<span dir="ltr">{formatDate(a.as_of)}</span>, {formatTime(a.as_of)}
              </>
            )}
          </p>
        )}
        <h2 className="text-lg font-bold">{a.provider}</h2>
        <p className="text-sm">{a.holder}</p>
        <Money value={amount} className={`mt-3 self-start text-[34px] leading-none font-bold ${tone}`} />
      </div>
      <p className="border-t border-hairline px-5 py-3 text-sm" dir="ltr">
        <span className="block text-right">{number}</span>
      </p>
    </section>
  );
}
