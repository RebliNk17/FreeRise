"use client";

import { Check } from "lucide-react";
import { Amount } from "@/components/Amount";
import { EmptyState, Status } from "@/components/Card";
import { send, type Review } from "@/lib/api";
import { categoryLabel, formatDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

/** "לבדיקה": transactions someone flagged to look at together; resolve clears them. */
export default function ReviewPage() {
  const { data, setData, error, reload } = useApi<Review[]>("/reviews");

  async function resolve(id: number) {
    setData((d) => d?.filter((r) => r.transaction_id !== id));
    await send("DELETE", `/transactions/${id}/review`).catch(() => reload());
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="page-title">לבדיקה</h1>
      <Status loading={!data} error={error} />
      {data?.length === 0 && <EmptyState text="אין עסקאות שמחכות לבדיקה." />}
      <ul className="flex flex-col gap-3">
        {data?.map((r) => (
          <li key={r.transaction_id} className="card flex flex-col gap-2 p-4">
            <div className="flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <p className="truncate font-bold">{r.description}</p>
                <p className="text-xs text-muted">
                  <span dir="ltr">{formatDate(r.date)}</span> · {r.account_label} · {categoryLabel(r.category_name)}
                </p>
              </div>
              <Amount value={r.amount} className="shrink-0 font-bold" />
            </div>
            <p className="rounded-2xl bg-sunken px-3 py-2 text-sm">
              <strong>{r.assignee ? `לבדוק עם ${r.assignee}` : "לבדיקה"}</strong>
              {r.note && ` · ${r.note}`}
            </p>
            <button type="button" className="btn-secondary self-start" onClick={() => resolve(r.transaction_id)}>
              <Check size={16} aria-hidden /> טופל
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
