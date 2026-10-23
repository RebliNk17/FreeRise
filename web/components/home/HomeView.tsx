"use client";

import { useState } from "react";
import { CycleSwitcher } from "@/components/CycleSwitcher";
import { Status } from "@/components/Card";
import { formatCycleRange, monthName } from "@/lib/format";
import type { Uncategorized } from "@/lib/api";
import { pendingCount } from "@/lib/categorize";
import { findTxn, isIdle, type HomeData, type Txn } from "@/lib/home";
import { useApi } from "@/lib/useApi";
import { useHiddenAccounts, withHidden } from "@/lib/viewFilter";
import { AccountFilter } from "./AccountFilter";
import { AddTrackedCategory } from "./AddTrackedCategory";
import { CategorizeChip, CategorizeSheet } from "./CategorizeSheet";
import { HomeContext, type HomeCtx } from "./context";
import { Expander } from "./Expander";
import { FixedCard } from "./FixedCard";
import { IncomeCard } from "./IncomeCard";
import { InsightCarousel } from "./InsightCarousel";
import { BalancesCard, NextCycleCard } from "./OutlookCards";
import { SectionHeader, TotalLine } from "./parts";
import { SavingsCard } from "./SavingsCard";
import { TrackedCategoryCard } from "./TrackedCategoryCard";
import { TxnList } from "./TxnRow";
import { TxnSheet } from "./TxnSheet";
import { VariableCard } from "./VariableCard";
import { WeeklySummary } from "./WeeklySummary";

/** The whole home screen for one cycle. path: "/home/current" or "/home/{y}/{m}". */
export function HomeView({ path, title }: { path: string; title: string }) {
  const hidden = useHiddenAccounts();
  const { data, setData, error, reload } = useApi<HomeData>(withHidden(path, hidden));
  const [sheet, setSheet] = useState<Txn | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const unc = useApi<Uncategorized[]>("/categories/uncategorized", version);
  // /home?categorize=1 (e.g. from the "waiting to be categorized" notification) opens the sheet.
  const [sorting, setSorting] = useState(() => typeof window !== "undefined" && new URLSearchParams(window.location.search).has("categorize"));

  if (!data)
    return (
      <div className="flex flex-col gap-4">
        <h1 className="section-title text-center">{title}</h1>
        <Status loading error={error} />
      </div>
    );

  const mutate: HomeCtx["mutate"] = async (optimistic, request) => {
    const prev = data;
    setFailed(false);
    setData((d) => d && optimistic(d));
    try {
      await request();
      return true;
    } catch {
      setData(() => prev);
      setFailed(true);
      return false;
    } finally {
      reload();
      setVersion((v) => v + 1);
    }
  };

  const { cycle } = data;
  const empty = data.total.spent === 0 && data.total.expected === 0 && data.income.received === 0 && data.income.expected === 0;
  const idle = data.tracked.filter(isIdle);
  const active = data.tracked.filter((c) => !isIdle(c));
  const open = sheet && (findTxn(data, sheet.id) ?? sheet);
  const weeks = data.variable.weeks;
  const week = weeks.findIndex((w) => w.is_current);

  return (
    <HomeContext value={{ data, mutate, openTxn: setSheet, version }}>
      <div className="flex flex-col gap-4">
        <CycleSwitcher
          prev={`/home/${cycle.prev.year}/${cycle.prev.month}`}
          next={cycle.next && !cycle.is_current ? `/home/${cycle.next.year}/${cycle.next.month}` : null}
          prevLabel="המחזור הקודם"
          nextLabel="המחזור הבא"
          title={`${monthName(cycle.label_month)} ${cycle.label_year}`}
          sub={
            <>
              <span dir="ltr">{formatCycleRange(cycle.start, cycle.end)}</span>
              {week >= 0 && ` · שבוע ${week + 1} מתוך ${weeks.length}`}
            </>
          }
        />
        <AccountFilter />
        {failed && (
          <p className="rounded-2xl bg-danger-soft px-4 py-3 text-sm font-semibold text-danger-strong" role="alert">
            השמירה נכשלה — השינוי בוטל.
          </p>
        )}
        {!empty && data.summary && <WeeklySummary s={data.summary} />}
        {cycle.is_current && <InsightCarousel />}
        <CategorizeChip count={pendingCount(unc.data ?? [])} onOpen={() => setSorting(true)} />
        <Status loading={false} error={false} empty={empty} />
        {!empty && (
          <>
            <SectionHeader title="הוצאות משתנות" />
            <VariableCard v={data.variable} />
            {active.length > 0 && (
              <ul className="card flex flex-col divide-y divide-hairline px-3.5 py-1.5" aria-label="קטגוריות במעקב">
                {active.map((c) => (
                  <li key={c.category_id}>
                    <TrackedCategoryCard c={c} />
                  </li>
                ))}
              </ul>
            )}
            {idle.length > 0 && (
              <Expander className="card px-4 py-2" buttonClassName="flex min-h-11" label={<span className="text-sm font-semibold text-muted">קטגוריות ללא פעילות ({idle.length})</span>}>
                <ul className="flex flex-col divide-y divide-hairline border-t border-hairline">
                  {idle.map((c) => (
                    <li key={c.category_id}>
                      <TrackedCategoryCard c={c} />
                    </li>
                  ))}
                </ul>
              </Expander>
            )}
            <AddTrackedCategory />
            <SavingsCard s={data.savings} />
            <FixedCard f={data.fixed} />
            <TotalLine spent={data.total.spent} expected={data.total.expected} />
            <IncomeCard inc={data.income} />
            {cycle.is_current && (
              <>
                <BalancesCard />
                <NextCycleCard />
              </>
            )}
          </>
        )}
        {data.moved_next.transactions.length > 0 && (
          <Expander className="card px-4 py-2" buttonClassName="flex min-h-11" label={<span className="text-sm font-semibold text-muted">הועברו לחודש הבא ({data.moved_next.transactions.length})</span>}>
            <div className="pt-2">
              <TxnList txns={data.moved_next.transactions} />
            </div>
          </Expander>
        )}
      </div>
      {open && <TxnSheet key={open.id} t={open} onClose={() => setSheet(null)} />}
      {sorting && unc.data && (
        <CategorizeSheet
          list={unc.data}
          onClose={(changed) => {
            setSorting(false);
            if (changed) {
              reload();
              setVersion((v) => v + 1);
            }
          }}
        />
      )}
    </HomeContext>
  );
}
