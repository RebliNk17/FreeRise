"use client";

import Link from "next/link";
import { CircleCheck, TriangleAlert } from "lucide-react";
import { Money } from "@/components/Amount";
import { Card } from "@/components/Card";
import { formatDate, monthName, txnCount } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Health = {
  ok: boolean;
  connections: { id: number; label: string; provider: string; owner: string; enabled: boolean; last_success_at: string | null; last_error: string | null; months_without_data: string[] }[];
  idle_accounts: { id: number; label: string; kind: string; last_txn: string | null }[];
  card_bills: { bank_txn_id: number; date: string; issuer: string; amount: number; status: "mismatch" | "unknown_card"; gap: number }[];
  uncategorized: number;
};

const ym = (s: string) => `${monthName(Number(s.slice(5, 7)))} ${s.slice(0, 4)}`;

/** "בדיקת תקינות": per connection last sync and months with no data, idle accounts, card bills that don't add up, uncategorized count. */
export function DataHealth() {
  const { data } = useApi<Health>("/data-health");
  if (!data) return null;
  return (
    <Card
      title="בדיקת תקינות"
      action={
        data.ok ? (
          <span className="chip bg-brand-soft text-brand">
            <CircleCheck size={14} aria-hidden /> הכל תקין
          </span>
        ) : (
          <span className="chip bg-sun-soft text-sun-strong">
            <TriangleAlert size={14} aria-hidden /> יש מה לבדוק
          </span>
        )
      }
    >
      <ul className="flex flex-col divide-y divide-hairline text-sm">
        {data.connections.map((c) => (
          <li key={c.id} className="flex flex-col gap-0.5 py-2.5">
            <div className="flex items-baseline gap-2">
              <span className="flex-1 font-bold">
                {c.label} <span className="font-normal text-muted">· {c.provider}</span>
              </span>
              <span className={`text-xs ${c.last_error ? "font-semibold text-danger" : "text-muted"}`}>
                {c.last_success_at ? (
                  <>
                    סונכרן <span dir="ltr">{formatDate(c.last_success_at)}</span>
                  </>
                ) : (
                  "עוד לא סונכרן"
                )}
              </span>
            </div>
            {!c.enabled && <p className="text-xs text-muted">מושבת</p>}
            {c.last_error && <p className="text-xs text-danger">הסנכרון האחרון נכשל</p>}
            {c.months_without_data.length > 0 && <p className="text-xs text-sun-strong">חודשים בלי נתונים: {c.months_without_data.map(ym).join(", ")}</p>}
          </li>
        ))}
      </ul>
      {data.idle_accounts.length > 0 && (
        <section className="flex flex-col gap-1 border-t border-hairline pt-3 text-sm">
          <h3 className="font-bold">חשבונות בלי פעילות ב־90 הימים האחרונים</h3>
          {data.idle_accounts.map((a) => (
            <p key={a.id} className="flex gap-2">
              <span className="flex-1">{a.label}</span>
              <span className="text-xs text-muted">
                {a.last_txn ? (
                  <>
                    אחרונה <span dir="ltr">{formatDate(a.last_txn)}</span>
                  </>
                ) : (
                  "אין עסקאות"
                )}
              </span>
            </p>
          ))}
        </section>
      )}
      {data.card_bills.length > 0 && (
        <section className="flex flex-col gap-1.5 border-t border-hairline pt-3 text-sm">
          <h3 className="font-bold">חיובי אשראי שלא מסתדרים</h3>
          {data.card_bills.map((b) => (
            <p key={b.bank_txn_id} className="text-[13px]">
              {b.status === "unknown_card" ? (
                <>
                  חיוב {b.issuer || "אשראי"} של <Money value={b.amount} className="font-bold" /> מ־<span dir="ltr">{formatDate(b.date)}</span> לכרטיס שלא מחובר.
                </>
              ) : (
                <>
                  חיוב {b.issuer} מ־<span dir="ltr">{formatDate(b.date)}</span> {b.gap > 0 ? "גבוה" : "נמוך"} ב־<Money value={Math.abs(b.gap)} className="font-bold" /> מהעסקאות שיש לנו.
                </>
              )}
            </p>
          ))}
        </section>
      )}
      {data.uncategorized > 0 && (
        <p className="border-t border-hairline pt-3 text-sm">
          {txnCount(data.uncategorized)} בלי קטגוריה ·{" "}
          <Link href="/home?categorize=1" className="link">
            לסיווג
          </Link>
        </p>
      )}
    </Card>
  );
}
