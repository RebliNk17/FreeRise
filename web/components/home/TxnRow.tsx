"use client";

import { EllipsisVertical, StickyNote } from "lucide-react";
import { Money } from "@/components/Amount";
import { formatDate } from "@/lib/format";
import { accountWithHolder, shiftChip, type Txn } from "@/lib/home";
import { useHome } from "./context";

/** Amount bold; description + account on the second line; date on the side; tap opens the sheet. */
export function TxnRow({ t, select }: { t: Txn; select?: { checked: boolean; onChange: (v: boolean) => void } }) {
  const { openTxn, data } = useHome();
  const body = (
    <>
      <span className="block min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <Money value={Math.abs(t.amount)} className={`font-bold ${t.amount > 0 && t.group !== "income" ? "text-positive" : ""}`} />
          {t.amount > 0 && t.group !== "income" && <span className="text-xs font-semibold text-positive">זיכוי</span>}
          {t.note && <StickyNote size={14} className="text-muted" aria-label="יש הערה" />}
          {t.status === "pending" && <span className="rounded-full bg-sunken px-2 text-[10px] font-semibold text-muted">בקליטה</span>}
          {shiftChip(t) && <span className="rounded-full bg-brand-soft px-2 text-[10px] font-semibold text-brand">{shiftChip(t)}</span>}
        </span>
        <span className="block truncate text-xs text-muted">
          {t.description} · {accountWithHolder(t, data.multi_holder)}
          {t.installment_total ? ` · תשלום ${t.installment_number}/${t.installment_total}` : ""}
        </span>
      </span>
      <span dir="ltr" className="shrink-0 text-xs text-muted">
        {formatDate(t.date)}
      </span>
    </>
  );
  if (select)
    return (
      <label className="flex min-h-12 cursor-pointer items-center gap-3 py-2.5">
        <input type="checkbox" className="size-4 accent-brand" checked={select.checked} onChange={(e) => select.onChange(e.target.checked)} />
        {body}
      </label>
    );
  return (
    <button type="button" className="flex min-h-12 w-full items-center gap-3 rounded-xl px-1 py-2.5 text-start hover:bg-sunken/50" onClick={() => openTxn(t)}>
      {body}
      <EllipsisVertical size={16} className="shrink-0 text-muted" aria-hidden />
    </button>
  );
}

export function TxnList({ txns, empty = "אין עסקאות" }: { txns: Txn[]; empty?: string }) {
  if (!txns.length) return <p className="py-2 text-sm text-muted">{empty}</p>;
  return (
    <ul className="flex flex-col divide-y divide-hairline">
      {txns.map((t) => (
        <li key={t.id}>
          <TxnRow t={t} />
        </li>
      ))}
    </ul>
  );
}
