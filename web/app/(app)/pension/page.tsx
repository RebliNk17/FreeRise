"use client";

import { useState } from "react";
import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { Amount } from "@/components/Amount";
import { BalanceChart } from "@/components/BalanceChart";
import { Card, Status } from "@/components/Card";
import { send, type Fund, type Funds } from "@/lib/api";
import { formatDate, formatPct, monthName, pctColor } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { announceSync, type RunRef } from "../sync/SyncToasts";

/** Sum fund balances per month (mislaka reports monthly; days may differ between funds). */
function totalByMonth(funds: Fund[]) {
  const byMonth = new Map<string, number>();
  for (const f of funds) for (const p of f.monthly) byMonth.set(p.date.slice(0, 7), (byMonth.get(p.date.slice(0, 7)) ?? 0) + p.balance);
  return [...byMonth].sort(([a], [b]) => a.localeCompare(b)).map(([m, balance]) => ({ date: `${m}-01`, balance }));
}

export default function PensionPage() {
  const { data, error } = useApi<Funds>("/pension/funds");
  const [msg, setMsg] = useState("");

  async function sync(credential_id: number) {
    try {
      const { runs } = await send<{ runs: RunRef[] }>("POST", "/sync", { credential_id });
      setMsg("");
      announceSync(runs, (data?.credentials ?? []).map((c) => ({ ...c, provider: "mislaka" })));
    } catch {
      setMsg("בקשת הסנכרון נכשלה.");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="page-title">פנסיה והשתלמות</h1>
      <Status loading={!data} error={error} empty={data && !data.funds.length && !data.credentials.length} />
      {data && (data.funds.length > 0 || data.credentials.length > 0) && (
        <>
          {data.funds.length > 0 && (
            <Card>
              <p className="text-sm text-muted">סה״כ חיסכון</p>
              <Amount value={data.total} plain className="text-[40px] leading-tight font-extrabold" />
              {data.as_of && (
                <p className="text-xs text-muted">
                  נכון ל-<span dir="ltr">{formatDate(data.as_of)}</span>
                </p>
              )}
              <BalanceChart data={totalByMonth(data.funds)} />
            </Card>
          )}
          {data.forecast
            .filter((r) => r.forecast_monthly_pension || r.forecast_lump_sum || r.forecast_total_balance)
            .map((r) => (
              <Card key={r.credential_id} title={`תחזית לגיל פרישה — ${r.owner}`}>
                <dl className="grid grid-cols-2 gap-2 text-sm">
                  {(
                    [
                      ["קצבה חודשית צפויה", r.forecast_monthly_pension],
                      ["סכום חד-פעמי בפרישה", r.forecast_lump_sum],
                      ["צבירה צפויה בפרישה", r.forecast_total_balance],
                      ["חיסכון נוכחי", r.total_savings],
                    ] as const
                  ).map(
                    ([label, v]) =>
                      !!v && (
                        <div key={label}>
                          <dt className="text-xs text-muted">{label}</dt>
                          <dd>
                            <Amount value={v} plain className="font-semibold" />
                          </dd>
                        </div>
                      ),
                  )}
                </dl>
                <p className="text-xs text-muted">
                  לפי דוח המסלקה לחודש {monthName(Number(r.report_month.slice(5, 7)))} {r.report_month.slice(0, 4)}, כפי שנמסר
                </p>
              </Card>
            ))}
          <ul className="flex flex-col gap-3">
            {data.funds.map((f) => (
              <li key={f.id}>
                <Link href={`/pension/${f.id}`} className="card flex items-start gap-3 p-4 hover:border-brand">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-bold">{f.name}</div>
                    <div className="text-xs text-muted">
                      {f.owner} · {f.product_type}
                      {f.company && ` · ${f.company}`}
                    </div>
                    {!!f.forecast_monthly_pension && (
                      <div className="text-xs text-muted">
                        קצבה צפויה <Amount value={f.forecast_monthly_pension} plain />
                      </div>
                    )}
                    {f.liquidity_date && (
                      <div className="text-xs text-muted">
                        נזיל ב-<span dir="ltr">{formatDate(f.liquidity_date)}</span>
                      </div>
                    )}
                  </div>
                  <div className="text-end">
                    <Amount value={f.latest_balance} plain className="font-semibold" />
                    <div dir="ltr" className={`text-xs ${pctColor(f.ytd_return_pct)}`}>
                      {formatPct(f.ytd_return_pct)} YTD
                    </div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
          {data.credentials.length > 0 && (
            <Card title="סנכרון">
              <div className="flex flex-wrap gap-2">
                {data.credentials.map((c) => (
                  <button key={c.id} className="btn-ghost" onClick={() => sync(c.id)}>
                    <RefreshCw size={14} /> סנכרן פנסיה — {c.owner}
                  </button>
                ))}
              </div>
              {msg && <p className="text-sm text-muted" role="status">{msg}</p>}
              <p className="text-xs text-muted">המסלקה מתעדכנת פעם בחודש (~20 לחודש)</p>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
