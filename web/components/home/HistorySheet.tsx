"use client";

import { useState } from "react";
import { ChartColumn } from "lucide-react";
import { Money } from "@/components/Amount";
import { Status } from "@/components/Card";
import { MonthBars } from "@/components/charts/MonthBars";
import { Sheet, SheetTitle } from "@/components/Sheet";
import { formatILS, monthName } from "@/lib/format";
import { historyPath, type HistoryKind, type HomeHistory } from "@/lib/history";
import { useApi } from "@/lib/useApi";
import { useHiddenAccounts } from "@/lib/viewFilter";
import { useHome } from "./context";

/** "חודשים קודמים" button for a home card; opens the spent-vs-expected sheet. */
export function HistoryButton({ kind, categoryId, title, labels = ["יצא", "צפוי"] }: { kind: HistoryKind; categoryId?: number; title: string; labels?: [string, string] }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="link flex min-h-11 items-center gap-1" onClick={() => setOpen(true)}>
        <ChartColumn size={15} aria-hidden /> חודשים קודמים
      </button>
      {open && <HistorySheet kind={kind} categoryId={categoryId} title={title} labels={labels} onClose={() => setOpen(false)} />}
    </>
  );
}

export function HistorySheet({ kind, categoryId, title, labels, onClose }: { kind: HistoryKind; categoryId?: number; title: string; labels: [string, string]; onClose: () => void }) {
  const { cycle } = useHome().data;
  const { data, error } = useApi<HomeHistory>(historyPath(kind, cycle, useHiddenAccounts(), categoryId));
  const bars = (data?.cycles ?? []).map((c) => ({ key: `${c.label_year}-${c.label_month}`, label: monthName(c.label_month).slice(0, 3), full: `${monthName(c.label_month)} ${c.label_year}`, value: c.spent, expected: c.expected }));
  const alt = bars.map((b) => `${b.full}: ${labels[0]} ${formatILS(b.value)}, ${labels[1]} ${formatILS(b.expected)}`).join("; ");
  return (
    <Sheet labelledBy="history-title" onClose={onClose} header={<SheetTitle id="history-title" title={`${title}: חודשים קודמים`} onClose={onClose} />}>
      <div className="flex flex-col gap-3">
        <Status loading={!data} error={error} />
        {data && (
          <>
            <div className="grid grid-cols-2 gap-2">
              <div className="card flex flex-col p-3">
                <span className="text-xs text-muted">ממוצע {labels[0]}</span>
                <Money value={data.avg_spent} className="text-xl font-extrabold" />
              </div>
              <div className="card flex flex-col p-3">
                <span className="text-xs text-muted">ממוצע {labels[1]}</span>
                <Money value={data.avg_expected} className="text-xl font-bold text-muted" />
              </div>
            </div>
            <div className="card p-3">
              <MonthBars data={bars} valueLabel={labels[0]} expectedLabel={labels[1]} overIsBad={kind !== "income" && kind !== "savings"} ariaLabel={alt} />
            </div>
            <ul className="card flex flex-col divide-y divide-hairline px-3.5 py-1 text-sm">
              {[...bars].reverse().map((b) => (
                <li key={b.key} className="flex min-h-11 items-center gap-2">
                  <span className="flex-1 font-semibold">{b.full}</span>
                  <Money value={b.value} className={`font-bold ${b.value > b.expected + 0.5 && kind !== "income" && kind !== "savings" ? "text-danger" : ""}`} />
                  <span className="text-xs text-muted">
                    מתוך <Money value={b.expected} />
                  </span>
                </li>
              ))}
            </ul>
            <p className="px-1 text-xs text-muted">{data.basis}</p>
          </>
        )}
      </div>
    </Sheet>
  );
}
