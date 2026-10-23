"use client";

import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { Money } from "@/components/Amount";
import { Card } from "@/components/Card";
import { ExpectedItems } from "@/components/ExpectedItems";
import type { Forecast, Plan } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useHiddenAccounts, withHidden } from "@/lib/viewFilter";
import { useHome } from "./context";
import { Expander } from "./Expander";

// ponytail: current-state data comes from the existing /plan/current and /forecast/next
// endpoints (current cycle only), so /api/home stays per-cycle.

/** "מצב העו״ש והאשראי": bank balance per account, total, upcoming card charges, fees. */
export function BalancesCard() {
  const { data } = useApi<Plan>(withHidden("/plan/current", useHiddenAccounts()), useHome().version);
  if (!data) return null;
  const b = data.balances;
  if (!b.accounts.length && !b.upcoming_card_charges) return null;
  return (
    <Card title="מצב העו״ש והאשראי">
      <ul className="flex flex-col gap-2 text-sm">
        {b.accounts.map((a) => (
          <li key={a.id} className="flex items-baseline gap-2">
            <span className="min-w-0 flex-1">
              <span className="block truncate">{a.display_name}</span>
              {a.as_of && (
                <span className="text-xs text-muted">
                  נכון ל־<span dir="ltr">{formatDate(a.as_of)}</span>
                </span>
              )}
            </span>
            <Money value={a.balance} className={`font-semibold ${a.balance < 0 ? "text-danger" : ""}`} />
          </li>
        ))}
        <li className="flex items-baseline border-t border-hairline pt-2 font-bold">
          <span className="flex-1">סה״כ בעו״ש</span>
          <Money value={b.bank_total} className={b.bank_total < 0 ? "text-danger" : ""} />
        </li>
        <li className="flex items-baseline">
          <span className="flex-1">חיובי אשראי קרובים</span>
          <Money value={b.upcoming_card_charges} className="font-semibold" />
        </li>
        {data.fees.total > 0 && (
          <li className="flex items-baseline text-muted">
            <span className="flex-1">עמלות החודש</span>
            <Money value={data.fees.total} />
          </li>
        )}
      </ul>
    </Card>
  );
}

/** "החודש הבא": installments that stop, expected fixed and income, link to /forecast. */
export function NextCycleCard() {
  const { data: f } = useApi<Forecast>("/forecast/next", useHome().version);
  if (!f) return null;
  return (
    <Card
      title="החודש הבא"
      action={
        <Link href="/forecast" className="link flex items-center">
          לתחזית המלאה <ChevronLeft size={16} aria-hidden />
        </Link>
      }
    >
      <ul className="flex flex-col gap-2 text-sm">
        <li className="flex items-baseline">
          <span className="flex-1">הוצאות קבועות צפויות</span>
          <Money value={f.fixed_total} className="font-semibold" />
        </li>
        <li className="flex items-baseline">
          <span className="flex-1">הכנסות צפויות</span>
          <Money value={f.income_total} className="font-semibold" />
        </li>
      </ul>
      {f.installments_stopping.length > 0 ? (
        <Expander
          buttonClassName="flex min-h-11 border-t border-hairline pt-2"
          label={
            <span className="text-sm font-semibold">
              יפסיקו תשלומים בסך <Money value={f.installments_stopping_total} className="font-bold text-positive" /> ({f.installments_stopping.length})
            </span>
          }
        >
          <div className="pt-1">
            <ExpectedItems items={f.installments_stopping} none="" />
          </div>
        </Expander>
      ) : (
        <p className="border-t border-hairline pt-3 text-sm text-muted">אין תשלומים שמסתיימים בחודש הבא.</p>
      )}
    </Card>
  );
}
