"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Info, RefreshCw, TrendingUp, TriangleAlert } from "lucide-react";
import { Amount } from "@/components/Amount";
import { BalanceChart } from "@/components/BalanceChart";
import { Card, Status } from "@/components/Card";
import { send, type DepositAlert, type Fund, type FundDepositRow, type Funds } from "@/lib/api";
import { formatDate, formatPercentValue, monthName } from "@/lib/format";
import { periodOf, summarize } from "@/lib/pension";
import { useApi } from "@/lib/useApi";
import { announceSync, type RunRef } from "../sync/SyncToasts";
import { GainsCard, Signed } from "./GainsCard";

const cents = (x: number) => Math.round(x * 100) / 100;
const sumOf = (xs: number[]) => cents(xs.reduce((s, x) => s + x, 0));
const today = () => new Date().toISOString().slice(0, 10);
const SECTIONS: Record<string, string> = {
  pension: "פנסיה",
  hishtalmut: "קרנות השתלמות",
  gemel: "קופות גמל",
};
/** "2026-09-01" → "2026-09-30": a month row's balance is its end. */
const monthEnd = (m: string) => {
  const [y, mo] = m.split("-").map(Number);
  return `${m.slice(0, 8)}${new Date(y, mo, 0).getDate()}`;
};
const monthLabel = (iso: string) => `${monthName(Number(iso.slice(5, 7)))} ${iso.slice(0, 4)}`;

/** Sum fund balances per month (funds report on different days). */
function totalByMonth(funds: Fund[]) {
  const byMonth = new Map<string, number>();
  for (const f of funds) for (const p of f.monthly) byMonth.set(p.date.slice(0, 7), (byMonth.get(p.date.slice(0, 7)) ?? 0) + p.balance);
  return [...byMonth].sort(([a], [b]) => a.localeCompare(b)).map(([m, balance]) => ({ date: `${m}-01`, balance }));
}

/** Liquid now: the portal's figure, else the whole balance once the liquidity date passed. */
const liquidNow = (f: Fund) => f.liquid_balance ?? (f.liquidity_date && f.liquidity_date <= today() ? f.latest_balance : 0);

/** Counts up to `value` once (900ms); exact value at the end, none under reduced motion. */
function CountUp({ value, className }: { value: number; className?: string }) {
  const [shown, setShown] = useState(value);
  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t0 = performance.now();
    let raf = 0;
    const step = (t: number) => {
      const k = Math.min((t - t0) / 900, 1);
      setShown(k === 1 ? value : cents(value * (1 - (1 - k) ** 3)));
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <Amount value={shown} plain className={className} />;
}

function Sparkline({ points }: { points: { balance: number }[] }) {
  if (points.length < 2) return null;
  const vs = points.map((p) => p.balance);
  const [min, max] = [Math.min(...vs), Math.max(...vs)];
  const d = vs.map((v, i) => `${(i / (vs.length - 1)) * 80},${26 - ((v - min) / (max - min || 1)) * 22}`).join(" ");
  return (
    <svg viewBox="0 0 80 28" className="h-7 w-20 shrink-0" aria-hidden>
      <polyline points={d} fill="none" stroke="var(--brand)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function AlertIcon({ kind }: { kind: DepositAlert["kind"] }) {
  if (kind === "up") return <TrendingUp size={18} aria-hidden className="text-positive" />;
  if (kind === "missing") return <TriangleAlert size={18} aria-hidden className="text-danger" />;
  return <Info size={18} aria-hidden className="text-sun-strong" />;
}

function FundRow({ f, ytd }: { f: Fund; ytd: number | null }) {
  const liquid = f.liquidity_date && f.liquidity_date <= today();
  return (
    <li>
      <Link href={`/pension/${f.id}`} className="flex items-center gap-3 border-t border-hairline py-3 hover:bg-sunken/50">
        <div className="min-w-0 flex-1">
          <div className="truncate font-bold">
            {f.name}
            {f.track && <span className="text-xs font-normal text-muted"> · {f.track}</span>}
          </div>
          <div className="text-xs text-muted">
            {[f.company, f.owner].filter(Boolean).join(" · ")}
            {!!f.forecast_monthly_pension && (
              <>
                {" · קצבה "}
                <Amount value={f.forecast_monthly_pension} plain />
              </>
            )}
            {f.liquidity_date &&
              (liquid ? (
                <span className="font-bold text-positive"> · נזיל</span>
              ) : (
                <>
                  {" · נזיל ב-"}
                  <span dir="ltr">{formatDate(f.liquidity_date)}</span>
                </>
              ))}
          </div>
        </div>
        <Sparkline points={f.monthly} />
        <div className="text-end">
          <Amount value={f.latest_balance} plain className="font-bold" />
          {ytd != null && <Signed value={ytd} className="block text-xs" />}
        </div>
      </Link>
    </li>
  );
}

function DepositsCard({ deposits, funds }: { deposits: FundDepositRow[]; funds: Map<number, Fund> }) {
  const months = new Map<string, FundDepositRow[]>();
  for (const d of deposits) months.set(d.date.slice(0, 7), [...(months.get(d.date.slice(0, 7)) ?? []), d]);
  const recent = [...months].slice(0, 3);
  if (!recent.length) return null;
  return (
    <Card title="הפקדות אחרונות" className="rise">
      {recent.map(([m, rows], i) => (
        <details key={m} open={i === 0} className="border-t border-hairline first:border-t-0">
          <summary className="flex cursor-pointer items-center justify-between gap-3 py-2">
            <span>
              <b>{monthLabel(`${m}-01`)}</b>
              <span className="text-xs text-muted"> · {rows.length === 1 ? "הפקדה אחת" : `${rows.length} הפקדות`}</span>
            </span>
            <Signed value={sumOf(rows.map((r) => r.amount))} className="font-bold" />
          </summary>
          <ul className="flex flex-col gap-2 pb-2">
            {rows.map((r, j) => {
              const f = funds.get(r.fund_id);
              const split = (
                [
                  ["מעסיק", r.employer_amount],
                  ["עובד", r.employee_amount],
                  ["פיצויים", r.compensation_amount],
                ] as const
              ).filter(([, v]) => v);
              return (
                <li key={j} className="flex items-start justify-between gap-3 text-sm">
                  <span className="min-w-0">
                    <span className="block font-semibold">
                      {f?.name} <span className="text-xs font-normal text-muted">· {f?.company}</span>
                    </span>
                    <span className="block text-xs text-muted">
                      <span dir="ltr">{formatDate(r.date)}</span>
                      {r.salary_month && ` · משכורת ${monthLabel(`${r.salary_month}-01`)}`}
                      {split.map(([label, v]) => (
                        <span key={label}>
                          {` · ${label} `}
                          <Amount value={v!} plain />
                        </span>
                      ))}
                    </span>
                  </span>
                  <Amount value={r.amount} plain className="shrink-0 font-semibold" />
                </li>
              );
            })}
          </ul>
        </details>
      ))}
    </Card>
  );
}

// Legal maximums (percent): pension 0.5% of savings / 6% of deposits; hishtalmut & gemel 2% / 4%.
const MAX_FEE = (f: Fund) => (f.product_type === "pension" ? { savings: 0.5, deposit: 6 } : { savings: 2, deposit: 4 });
const yearAgo = () => new Date(Date.now() - 365 * 864e5).toISOString().slice(0, 10);
/** Which of several same-named funds this is: its track, else when it becomes liquid. */
const fundHint = (f: Fund) => f.track ?? (f.liquidity_date ? `נזיל ב-${formatDate(f.liquidity_date)}` : f.company);

function FeesCard({ funds, deposits }: { funds: Fund[]; deposits: FundDepositRow[] }) {
  const since = yearAgo();
  const rows = funds.map((f) => {
    const dep12 = sumOf(deposits.filter((d) => d.fund_id === f.id && d.date > since).map((d) => d.amount));
    const fromSavings = cents((f.latest_balance * (f.fee_savings_pct ?? 0)) / 100);
    const fromDeposits = cents((dep12 * (f.fee_deposit_pct ?? 0)) / 100);
    return { f, dep12, fromSavings, fromDeposits, total: cents(fromSavings + fromDeposits) };
  });
  const total = sumOf(rows.map((r) => r.total));
  const top = Math.max(...rows.map((r) => r.total), 1);
  const year = Math.max(0, ...funds.flatMap((f) => f.yearly_movements.filter((y) => y.management_fees != null).map((y) => Number(y.year))));
  const report = (f: Fund) => f.yearly_movements.find((y) => Number(y.year) === year);
  const paid = sumOf(funds.map((f) => report(f)?.management_fees ?? 0));
  const insurance = sumOf(funds.map((f) => report(f)?.insurance_costs ?? 0));
  const covers = funds.flatMap((f) => f.insurance_covers.map((c) => ({ ...c, fund: f })));
  return (
    <Card title="דמי ניהול וביטוח" className="rise">
      <div className="rounded-2xl bg-sunken px-3.5 py-3">
        <p className="text-sm text-muted">דמי ניהול בשנה, בערך</p>
        <Amount value={total} plain className="text-[28px] leading-tight font-extrabold" />
        <p className="text-xs text-muted">לפי היתרה היום וההפקדות של 12 החודשים האחרונים</p>
        {year > 0 && (
          <p className="mt-1 text-xs">
            בפועל שולמו ב-{year}: <Amount value={paid} plain className="font-bold" />
          </p>
        )}
      </div>
      <dl className="grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-xl border border-hairline px-3 py-2">
          <dt className="font-bold">מצבירה</dt>
          <dd className="text-muted">אחוז בשנה מכל הכסף שבקרן</dd>
        </div>
        <div className="rounded-xl border border-hairline px-3 py-2">
          <dt className="font-bold">מהפקדה</dt>
          <dd className="text-muted">אחוז מכל הפקדה חודשית</dd>
        </div>
      </dl>
      <ul className="flex flex-col">
        {rows.map(({ f, dep12, fromSavings, fromDeposits, total: t }) => {
          const max = MAX_FEE(f);
          return (
            <li key={f.id} className="flex flex-col gap-1.5 border-t border-hairline py-3">
              <div className="flex items-baseline justify-between gap-3">
                <span className="min-w-0 truncate font-semibold">
                  {f.name} <span className="text-xs font-normal text-muted">· {fundHint(f)}</span>
                </span>
                <span className="shrink-0 text-end">
                  <Amount value={t} plain className="font-bold" />
                  <span className="text-xs text-muted"> בשנה</span>
                </span>
              </div>
              <span className="block h-1.5 overflow-hidden rounded-full bg-sunken">
                <span className="grow-x block h-full rounded-full bg-sun" style={{ width: `${(t / top) * 100}%` }} />
              </span>
              <p className="text-xs text-muted">
                {formatPercentValue(f.fee_savings_pct)} מצבירה (<Amount value={fromSavings} plain />)
                {!!f.fee_deposit_pct && (
                  <>
                    {" + "}
                    {formatPercentValue(f.fee_deposit_pct)} מהפקדה (<Amount value={fromDeposits} plain /> מתוך <Amount value={dep12} plain />)
                  </>
                )}
                <span className="block text-faint">
                  מקסימום בחוק: {max.savings}% מצבירה, {max.deposit}% מהפקדה
                  {!!f.investment_expense_pct && ` · ועוד ${formatPercentValue(f.investment_expense_pct)} הוצאות השקעה`}
                </span>
                {report(f)?.management_fees != null && (
                  <span className="block">
                    שולם ב-{year}: <Amount value={report(f)!.management_fees!} plain />
                  </span>
                )}
              </p>
            </li>
          );
        })}
      </ul>
      <div className="flex flex-col gap-1.5 border-t border-hairline pt-3">
        <p className="section-title text-[15px]">ביטוח בקרן הפנסיה</p>
        {year > 0 && insurance > 0 && (
          <p className="text-sm">
            עלות הביטוח ב-{year}: <Amount value={insurance} plain className="font-bold" />
          </p>
        )}
        {covers.length > 0 ? (
          covers.map((c, i) => (
            <div key={i} className="flex justify-between gap-3 text-sm">
              <span>
                {c.title} <span className="text-xs text-muted">· {c.fund.name}</span>
              </span>
              <span className="text-end text-xs">
                {!!c.insured_amount && <Amount value={c.insured_amount} plain className="block text-sm font-semibold" />}
                {!!c.monthly_cost && (
                  <span className="text-muted">
                    <Amount value={c.monthly_cost} plain /> לחודש
                  </span>
                )}
              </span>
            </div>
          ))
        ) : (
          <p className="text-xs text-muted">חלק מההפקדה לפנסיה הולך לביטוח נכות ושארים. הכיסויים והעלות יופיעו אחרי הסנכרון הבא של מגדל.</p>
        )}
      </div>
    </Card>
  );
}

function DetailsCard({ funds, deposits }: { funds: Fund[]; deposits: FundDepositRow[] }) {
  const insured = deposits.find((d) => d.insured_salary);
  const latest = deposits.length ? deposits.filter((d) => d.date.slice(0, 7) === deposits[0].date.slice(0, 7) && d.employer_amount != null) : [];
  const employerShare = latest.length
    ? sumOf(latest.map((d) => (d.employer_amount ?? 0) + (d.compensation_amount ?? 0))) / sumOf(latest.map((d) => d.amount))
    : null;
  const liquid = sumOf(funds.map(liquidNow));
  const since = funds
    .map((f) => f.start_date)
    .filter(Boolean)
    .sort()[0];
  // Same employer is spelled "בע\"מ" by one fund and "בעמ" by another.
  const norm = (n: string) =>
    n
      .replace(/["״׳']/g, "")
      .replace(/\s+/g, " ")
      .trim();
  const names = new Map<string, string>();
  for (const n of [...deposits.map((d) => d.employer), ...funds.map((f) => f.employer)]) if (n && !names.has(norm(n))) names.set(norm(n), n);
  const [current, ...previous] = [...names.values()]; // deposits are newest first, so the first is the current one
  const tiles: { t: string; v: React.ReactNode; sub: React.ReactNode; wide?: boolean }[] = [];
  if (insured)
    tiles.push({
      t: "שכר מבוטח",
      v: <Amount value={insured.insured_salary!} plain />,
      sub: insured.salary_month ? `משכורת ${monthLabel(`${insured.salary_month}-01`)}` : formatDate(insured.date),
    });
  if (employerShare) tiles.push({ t: "חלק המעסיק בהפקדה", v: `${(employerShare * 100).toFixed(2)}%`, sub: "כולל פיצויים" });
  tiles.push({ t: "נזיל עכשיו", v: <Amount value={liquid} plain />, sub: "השאר נעול עד הפרישה או תאריך הנזילות" });
  if (since) {
    const [y, m] = since.split("-").map(Number);
    const now = new Date();
    const months = (now.getFullYear() - y) * 12 + now.getMonth() + 1 - m;
    const [yy, mm] = [Math.floor(months / 12), months % 12];
    tiles.push({
      t: "ותק בחיסכון",
      v: [yy && (yy === 1 ? "שנה" : `${yy} שנים`), mm && (mm === 1 ? "חודש" : `${mm} חודשים`)].filter(Boolean).join(" ו-") || "פחות מחודש",
      sub: (
        <>
          מאז <span dir="ltr">{formatDate(since)}</span>, ההצטרפות הראשונה
        </>
      ),
    });
  }
  if (current)
    tiles.push({
      t: "מעסיק נוכחי",
      v: current,
      wide: true,
      sub: previous.length > 0 && (
        <>
          קודמים:
          {previous.map((n) => (
            <span key={n} className="block">
              {n}
            </span>
          ))}
        </>
      ),
    });
  return (
    <Card title="פרטים חשובים" className="rise">
      <div className="grid grid-cols-2 gap-2">
        {tiles.map(({ t, v, sub, wide }) => (
          <div key={t} className={`rounded-2xl bg-sunken px-3 py-2.5 ${wide ? "col-span-2" : ""}`}>
            <p className="text-xs text-muted">{t}</p>
            <p className="font-display text-lg font-bold">{v}</p>
            <p className="text-xs text-faint">{sub}</p>
          </div>
        ))}
      </div>
    </Card>
  );
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

  const year = new Date().getFullYear();
  const yearGains = data ? summarize(data.gains, periodOf(`${year}-01-01`, "y")) : null;
  // The chip's gain month by month: 0 on Dec 31, then each month's end.
  let run = 0;
  const cumulative = yearGains?.months.length
    ? [
        { date: `${year - 1}-12-31`, balance: 0, label: "רווח מצטבר" },
        ...yearGains.months.map((m) => ({ date: monthEnd(m.month), balance: (run = cents(run + m.gain)), label: "רווח מצטבר" })),
      ]
    : [];
  const report = data ? data.funds.flatMap((f) => f.yearly_movements.filter((y) => Number(y.year) === year)) : [];
  // This year's gain: our month-end snapshots, else the funds' own report, else Modified Dietz YTD.
  // This year's gain per fund: our month-end balances, else the funds' own report, else Modified Dietz YTD.
  // A fund inside a group (Phoenix reports its funds only as a sum) has no gain of its own.
  const grouped = new Set(data?.gains.filter((g) => g.fund_ids.length > 1).flatMap((g) => g.fund_ids));
  const ytdOf = (f: Fund) =>
    grouped.has(f.id)
      ? null
      : (yearGains?.bySeries.get(String(f.id)) ?? f.yearly_movements.find((y) => Number(y.year) === year)?.gains ?? f.ytd_profit ?? null);
  const groupYtd = yearGains ? [...yearGains.bySeries].filter(([k]) => k.includes(",")).map(([, v]) => v) : [];
  const ytd = data ? [...data.funds.map(ytdOf).filter((x): x is number => x != null), ...groupYtd] : [];
  const ytdDeposits = report.length ? sumOf(report.map((y) => y.deposits ?? 0)) : null;
  const byId = new Map(data?.funds.map((f) => [f.id, f]));
  const groups = data
    ? [...new Set(data.funds.map((f) => f.product_type))].map((t) => ({
        t,
        funds: data.funds.filter((f) => f.product_type === t),
      }))
    : [];

  return (
    <div className="flex flex-col gap-4">
      <h1 className="page-title">פנסיה והשתלמות</h1>
      <Status loading={!data} error={error} empty={data && !data.funds.length && !data.credentials.length} />
      {data && (data.funds.length > 0 || data.credentials.length > 0) && (
        <>
          {data.funds.length > 0 && (
            <Card className="rise">
              <p className="text-sm text-muted">סה״כ חיסכון</p>
              <CountUp value={data.total} className="text-[40px] leading-tight font-extrabold" />
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                {ytd.length > 0 && (
                  <span className="chip bg-brand-soft text-brand">
                    <Signed value={sumOf(ytd)} /> מתחילת {year}
                  </span>
                )}
                {ytdDeposits != null && (
                  <span>
                    הופקדו <Amount value={ytdDeposits} plain />
                  </span>
                )}
                {data.as_of && (
                  <span>
                    נכון ל-<span dir="ltr">{formatDate(data.as_of)}</span>
                  </span>
                )}
              </div>
              {cumulative.length > 2 ? (
                <>
                  <BalanceChart data={cumulative} />
                  <p className="text-xs text-muted">רווח מצטבר מתחילת {year}, לפי החודשים שיש עליהם נתונים</p>
                </>
              ) : (
                <BalanceChart data={totalByMonth(data.funds)} />
              )}
            </Card>
          )}

          {data.deposit_alerts.length > 0 && (
            <Card title="בדיקת הפקדות" className="rise">
              <ul className="flex flex-col gap-3">
                {data.deposit_alerts.map((a) => (
                  <li key={`${a.kind}:${a.fund_id}:${a.month}:${a.body}`}>
                    <Link href={`/pension/${a.fund_id}`} className="flex items-start gap-3">
                      <span className="mt-0.5 shrink-0">
                        <AlertIcon kind={a.kind} />
                      </span>
                      <span className="min-w-0">
                        <span className="block text-sm font-bold">{a.title}</span>
                        <span className="block text-sm text-muted">{a.body}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {groups.map(({ t, funds }) => {
            const subtotal = sumOf(funds.map((f) => f.latest_balance));
            const pension = sumOf(funds.map((f) => f.forecast_monthly_pension ?? 0));
            const liquid = sumOf(funds.map(liquidNow));
            const sorted = t === "pension" ? funds : [...funds].sort((a, b) => (a.liquidity_date ?? "9").localeCompare(b.liquidity_date ?? "9"));
            // A provider's whole-portfolio history (Phoenix) charts the section when it covers only these funds.
            const ids = new Set(funds.map((f) => f.id));
            const history = data.gains
              .filter((g) => g.fund_ids.length > 1 && g.fund_ids.every((id) => ids.has(id)))
              .map((g) => ({ date: monthEnd(g.month), balance: g.end_balance }));
            return (
              <Card key={t} className="rise">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="section-title">{SECTIONS[t] ?? "חיסכון"}</h2>
                    <p className="text-xs text-muted">
                      <span dir="ltr">{((subtotal / data.total) * 100).toFixed(2)}%</span> מהחיסכון
                    </p>
                  </div>
                  <div className="text-end">
                    <Amount value={subtotal} plain className="text-xl font-bold" />
                    {liquid > 0 && (
                      <div>
                        <span className="chip mt-1 bg-brand-soft text-brand">
                          נזיל עכשיו <Amount value={liquid} plain />
                        </span>
                      </div>
                    )}
                  </div>
                </div>
                {pension > 0 && (
                  <div className="rounded-2xl bg-sun-soft px-3.5 py-3">
                    <p className="flex items-baseline justify-between gap-2 text-sm">
                      <span>קצבה חודשית צפויה בפרישה</span>
                      <Amount value={pension} plain className="text-xl font-bold" />
                    </p>
                    <p className="text-xs text-muted">לפי הקרנות</p>
                  </div>
                )}
                {history.length > 1 && <BalanceChart data={history} />}
                <ul className="flex flex-col">
                  {sorted.map((f) => (
                    <FundRow key={f.id} f={f} ytd={ytdOf(f)} />
                  ))}
                </ul>
              </Card>
            );
          })}

          <GainsCard funds={data.funds} gains={data.gains} />
          <DepositsCard deposits={data.deposits} funds={byId} />
          {data.funds.length > 0 && <FeesCard funds={data.funds} deposits={data.deposits} />}
          {data.funds.length > 0 && <DetailsCard funds={data.funds} deposits={data.deposits} />}

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

          {data.credentials.length > 0 && (
            <Card title="סנכרון">
              <div className="flex flex-wrap gap-2">
                {data.credentials.map((c) => (
                  <button key={c.id} className="btn-ghost" onClick={() => sync(c.id)}>
                    <RefreshCw size={14} /> סנכרן פנסיה — {c.owner}
                  </button>
                ))}
              </div>
              {msg && (
                <p className="text-sm text-muted" role="status">
                  {msg}
                </p>
              )}
              <p className="text-xs text-muted">מגדל והפניקס מתעדכנים אוטומטית פעם ביום. המסלקה מתעדכנת פעם בחודש (~20 לחודש) ודורשת קוד SMS.</p>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
