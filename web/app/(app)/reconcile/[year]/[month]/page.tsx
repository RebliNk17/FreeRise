"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Check, TriangleAlert } from "lucide-react";
import { Amount } from "@/components/Amount";
import { Card, Status, EmptyState } from "@/components/Card";
import { CycleSwitcher } from "@/components/CycleSwitcher";
import type { BillReconciliation, Reconcile } from "@/lib/api";
import { formatCycleRange, formatDate, monthName } from "@/lib/format";
import { providerName } from "@/lib/providers";
import { useApi } from "@/lib/useApi";

function shift(y: number, m: number, d: number) {
  const i = y * 12 + (m - 1) + d;
  return `/reconcile/${Math.floor(i / 12)}/${(i % 12) + 1}`;
}

export default function ReconcileMonth() {
  const params = useParams<{ year: string; month: string }>();
  const y = Number(params.year);
  const m = Number(params.month);
  const { data, error } = useApi<Reconcile>(`/reconcile/${y}/${m}`);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="page-title">התאמת חיובי אשראי</h1>
      <CycleSwitcher level="h2" prev={shift(y, m, -1)} next={shift(y, m, 1)} title={data ? `${monthName(Number(data.cycle.start.slice(5, 7)))} ${data.cycle.start.slice(0, 4)}` : `${monthName(m)} ${y}`} sub={data && <span dir="ltr">{formatCycleRange(data.cycle.start, data.cycle.end)}</span>} />
      <Status loading={!data} error={error} />
      {data && data.bills.length === 0 && <EmptyState text="אין חיובי אשראי בחשבון הבנק במחזור הזה." />}
      {data && data.bills.length > 0 && (
        <p className="text-sm text-muted">
          {data.matched_count} תואמים · {data.mismatch_count} לא תואמים · {data.unknown_count} מכרטיס לא מחובר
        </p>
      )}
      {data?.bills.map((b) => <BillCard key={b.bank_txn_id} b={b} />)}
    </div>
  );
}

function BillCard({ b }: { b: BillReconciliation }) {
  const ok = b.status === "matched";
  const issuer = b.issuer ? providerName(b.issuer) : "לא ידוע";
  return (
    <Card
      title={
        <>
          {issuer} · <span dir="ltr">{formatDate(b.date)}</span>
        </>
      }
      action={
        <span className={`chip ${ok ? "bg-brand-soft text-brand" : "bg-danger-soft text-danger-strong"}`}>
          {ok ? <Check size={14} aria-hidden /> : <TriangleAlert size={14} aria-hidden />}
          {ok ? "תואם" : b.status === "mismatch" ? "פער" : "לא מחובר"}
        </span>
      }
    >
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
        <span>
          בבנק <Amount value={b.amount} plain className="font-semibold" />
        </span>
        {b.status !== "unknown_card" && (
          <span>
            בכרטיס <Amount value={b.card_total} plain className="font-semibold" />
          </span>
        )}
        {b.status === "mismatch" && (
          <span className="text-danger">
            פער <Amount value={b.gap} plain className="font-semibold" />
          </span>
        )}
      </div>
      {b.status === "unknown_card" ? (
        <p className="text-sm text-danger">
          {b.issuer ? `כרטיס של ${issuer}` : "כרטיס לא מזוהה"} חויב מהבנק אבל אין כרטיס מחובר שתואם —{" "}
          <Link href="/settings/credentials" className="underline">
            חיבור כרטיס
          </Link>
        </p>
      ) : (
        <p className="text-xs text-muted">
          {b.matched_accounts.map((a) => a.name + (a.excluded ? " (מוחרג)" : "")).join(", ")}
        </p>
      )}
      {b.suggestions.length > 0 && (
        <div className="flex flex-col gap-1 text-sm">
          <span className="font-bold">עסקאות שאולי חסרות:</span>
          <ul className="flex flex-col">
            {b.suggestions.map((s) => (
              <li key={s.txn_id}>
                <Link href={`/transactions?${new URLSearchParams({ from: s.date, to: s.date, account_id: String(s.account_id), include_excluded: "true", label: s.description })}`} className="flex min-h-10 items-baseline gap-2 rounded-xl px-2 py-2 hover:bg-sunken/60">
                  <span className="flex-1 truncate">
                    {s.description} <span className="text-xs text-muted">· {s.reason}</span>
                  </span>
                  <Amount value={s.amount} />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
