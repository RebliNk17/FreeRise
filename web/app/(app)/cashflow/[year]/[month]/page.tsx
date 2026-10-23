"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { MonthBars } from "@/components/charts/MonthBars";
import { Amount } from "@/components/Amount";
import { Card, Status } from "@/components/Card";
import { CycleSwitcher } from "@/components/CycleSwitcher";
import { GROUP_LABEL } from "@/components/CategorySelect";
import type { CashFlow, Fees } from "@/lib/api";
import { categoryLabel, formatCycleRange, formatDate, formatILS, monthName, txnCount } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const GROUP_ORDER = ["variable", "fixed", "savings", "income"] as const;

function shift(y: number, m: number, d: number) {
  const i = y * 12 + (m - 1) + d;
  return `/cashflow/${Math.floor(i / 12)}/${(i % 12) + 1}`;
}

function txnLink(categoryId: number | null, name: string, start: string, end: string) {
  const p = new URLSearchParams({ from: start, to: end, label: categoryLabel(name) });
  if (categoryId == null) p.set("uncategorized", "true");
  else p.set("category_id", String(categoryId));
  return `/transactions?${p}`;
}

export default function CashFlowMonth() {
  const params = useParams<{ year: string; month: string }>();
  const y = Number(params.year);
  const m = Number(params.month);
  const { data, error } = useApi<CashFlow>(`/cashflow/${y}/${m}`);
  const empty = data && data.income === 0 && data.spending === 0 && data.groups.every((g) => g.categories.length === 0);

  return (
    <div className="flex flex-col gap-4">
      <CycleSwitcher prev={shift(y, m, -1)} next={shift(y, m, 1)} title={data ? `${monthName(Number(data.cycle.start.slice(5, 7)))} ${data.cycle.start.slice(0, 4)}` : `${monthName(m)} ${y}`} sub={data && <span dir="ltr">{formatCycleRange(data.cycle.start, data.cycle.end)}</span>} />
      <Status loading={!data} error={error} empty={empty} />
      {data && !empty && <CashFlowView cf={data} />}
    </div>
  );
}

function CashFlowView({ cf }: { cf: CashFlow }) {
  // Same source as the heading: the cycle's start month.
  const name = monthName(Number(cf.cycle.start.slice(5, 7)));
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const ended = cf.cycle.end < today;
  const positive = cf.verdict === "positive";
  const headline = positive
    ? ended
      ? `מעולה! ${name} הסתיים בתזרים חיובי`
      : `${name} בתזרים חיובי עד כה`
    : ended
      ? `${name} הסתיים בתזרים שלילי`
      : `${name} בתזרים שלילי עד כה`;
  const history = cf.history.map((h) => ({ key: h.start, label: monthName(Number(h.start.slice(5, 7))).slice(0, 3), full: `${monthName(h.label_month)} ${h.label_year}`, net: h.net, current: h.start === cf.cycle.start }));

  const chartAlt = history.map((h) => `${h.full}: ${formatILS(h.net)}`).join(", ");

  return (
    <>
      <Card>
        <p className="font-bold">{headline}</p>
        <Amount value={cf.net} plain className={`text-[40px] leading-tight font-extrabold ${positive ? "text-positive" : "text-danger"}`} />
        <div className="flex flex-wrap gap-2 text-[13px]">
          <span className="chip bg-brand-soft px-3 py-1.5 font-semibold text-brand">
            הכנסות <Amount value={cf.income} plain className="font-bold" />
          </span>
          <span className="chip bg-sunken px-3 py-1.5 font-semibold text-text">
            הוצאות <Amount value={-Math.abs(cf.spending)} className="font-bold" />
          </span>
        </div>
        {cf.pending_count > 0 && <p className="text-xs text-muted">{txnCount(cf.pending_count)} עדיין בהמתנה</p>}
      </Card>

      {cf.uncategorized_count > 0 && (
        <Link href="/home?categorize=1" className="rounded-2xl bg-sun-soft px-4 py-3 text-sm font-semibold">
          {cf.uncategorized_count === 1 ? "עסקה אחת לא מסווגת" : `${cf.uncategorized_count} עסקאות לא מסווגות`} (<Amount value={cf.uncategorized_total} plain />) — לסיווג
        </Link>
      )}

      {cf.fees.total > 0 && <FeesCard fees={cf.fees} />}

      <Card title={`${name} ביחס לחודשים אחרים`}>
        <MonthBars data={history.map((h) => ({ ...h, value: h.net }))} kind="net" valueLabel="נשאר בסוף החודש" ariaLabel={chartAlt} currentKey={history.find((h) => h.current)?.key} />
      </Card>

      <Card title="סיכום הוצאות חודשיות">
        {GROUP_ORDER.map((g) => {
          const group = cf.groups.find((x) => x.group === g);
          if (!group) return null;
          return (
            <details key={g} open={g === "variable"} className="group border-t border-hairline pt-2 first-of-type:border-0 first-of-type:pt-0">
              <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 py-1 font-bold">
                <span className="flex-1">{GROUP_LABEL[g]}</span>
                <Amount value={group.total} plain />
              </summary>
              {g === "income" && (
                <div className="flex gap-6 px-2 pb-1 text-xs text-muted">
                  <span>
                    הכנסות קבועות <Amount value={cf.income_fixed} plain />
                  </span>
                  <span>
                    הכנסות משתנות <Amount value={cf.income_variable} plain />
                  </span>
                </div>
              )}
              <ul className="flex flex-col pb-1 text-sm">
                {group.categories.map((c) => (
                  <li key={c.category_id ?? c.name}>
                    <Link href={txnLink(c.category_id, c.name, cf.cycle.start, cf.cycle.end)} className="flex min-h-10 items-baseline gap-2 rounded-xl px-2 py-2 hover:bg-sunken/60">
                      <span className="flex-1 truncate">{categoryLabel(c.name)}</span>
                      <span className="text-xs text-faint">{c.count}</span>
                      <Amount value={c.total} plain />
                    </Link>
                  </li>
                ))}
              </ul>
            </details>
          );
        })}
      </Card>
      {cf.basis && <p className="px-1 text-xs text-muted">{cf.basis}</p>}
    </>
  );
}

function FeesCard({ fees }: { fees: Fees }) {
  const delta = fees.total - fees.previous_total;
  const isNew = new Set(fees.new_fee_merchants);
  return (
    <Card title="עמלות ששולמו" action={<Amount value={fees.total} plain className="font-bold text-danger" />}>
      <p className="text-xs text-muted">
        {fees.count === 1 ? "חיוב אחד" : `${fees.count} חיובים`}
        {delta !== 0 && (
          <>
            {" "}· {delta > 0 ? "יותר" : "פחות"} מהחודש הקודם ב-<Amount value={Math.abs(delta)} plain />
          </>
        )}
      </p>
      <ul className="flex flex-col text-sm">
        {fees.items.map((x) => (
          <li key={x.txn_id}>
            <Link href={`/transactions?${new URLSearchParams({ from: x.date, to: x.date, account_id: String(x.account_id), label: x.description })}`} className="flex min-h-10 items-baseline gap-2 rounded-xl px-2 py-2 hover:bg-sunken/60">
              <span dir="ltr" className="text-xs text-muted">
                {formatDate(x.date)}
              </span>
              <span className="min-w-0 flex-1 truncate">
                {x.description}
                {isNew.has(x.fee_key) && <span className="text-xs text-danger"> · חדש</span>}
                <span className="block truncate text-xs text-muted">{x.account_name}</span>
              </span>
              <Amount value={x.amount} plain />
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
