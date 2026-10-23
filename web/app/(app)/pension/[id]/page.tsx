"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { Amount } from "@/components/Amount";
import { BalanceChart } from "@/components/BalanceChart";
import { Card, Status } from "@/components/Card";
import type { FundDetail } from "@/lib/api";
import { formatDate, formatPct, formatPercentValue, pctColor } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function FundPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = useApi<FundDetail>(`/pension/funds/${id}`);
  const f = data?.fund;

  return (
    <div className="flex flex-col gap-4">
      <Link href="/pension" className="flex items-center gap-1 text-sm text-muted">
        <ChevronRight size={16} /> פנסיה והשתלמות
      </Link>
      <Status loading={!data} error={error} />
      {f && data && (
        <>
          <Card>
            <h1 className="page-title">{f.name}</h1>
            <p className="text-xs text-muted">
              {f.owner} · {f.product_type}
              {f.company && ` · ${f.company}`} · פוליסה <span dir="ltr">{f.policy_id}</span>
            </p>
            <Amount value={f.latest_balance} plain className="text-[34px] leading-tight font-extrabold" />
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <dt className="text-xs text-muted">רווח מתחילת השנה</dt>
                <dd>
                  <Amount value={f.ytd_profit} /> <span dir="ltr" className="text-xs">({formatPct(f.ytd_return_pct)})</span>
                </dd>
              </div>
              {f.liquidity_date && (
                <div>
                  <dt className="text-xs text-muted">מועד נזילות</dt>
                  <dd dir="ltr" className="text-end">{formatDate(f.liquidity_date)}</dd>
                </div>
              )}
              <div>
                <dt className="text-xs text-muted">דמי ניהול מהפקדה</dt>
                <dd dir="ltr" className="text-end">{formatPercentValue(f.fee_deposit_pct)}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">דמי ניהול מצבירה</dt>
                <dd dir="ltr" className="text-end">{formatPercentValue(f.fee_savings_pct)}</dd>
              </div>
            </dl>
            <BalanceChart data={f.monthly} />
          </Card>

          {data.yearly.length > 0 && (
            <Card title="לפי שנה">
              <div className="-mx-4 overflow-x-auto px-4">
                <table className="w-full min-w-[480px] text-sm">
                  <thead className="text-xs text-muted">
                    <tr className="text-start">
                      <th className="py-1 text-start font-normal">שנה</th>
                      <th className="font-normal">יתרת פתיחה</th>
                      <th className="font-normal">הפקדות</th>
                      <th className="font-normal">רווח</th>
                      <th className="font-normal">יתרת סגירה</th>
                      <th className="font-normal">תשואה</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {data.yearly.map((y) => (
                      <tr key={y.year} className="text-center">
                        <td className="py-1.5 text-start font-semibold">{y.year}</td>
                        <td><Amount value={y.start_balance} plain /></td>
                        <td><Amount value={y.deposits} plain /></td>
                        <td><Amount value={y.profit} /></td>
                        <td><Amount value={y.end_balance} plain /></td>
                        <td dir="ltr" className={pctColor(y.return_pct)}>{formatPct(y.return_pct)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
