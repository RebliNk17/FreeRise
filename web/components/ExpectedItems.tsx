import { Amount } from "@/components/Amount";
import type { ForecastItem } from "@/lib/api";
import { categoryLabel, formatDate } from "@/lib/format";

/** Expected charges / income, each with the account it should come from (or land in). */
export function ExpectedItems({ items, none, income = false }: { items: ForecastItem[]; none: string; income?: boolean }) {
  if (!items.length) return <p className="text-sm text-muted">{none}</p>;
  return (
    <ul className="flex flex-col divide-y divide-hairline text-sm">
      {items.map((it, i) => (
        <li key={i} className="flex items-start gap-2 py-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="truncate font-bold">{it.label}</span>
              {it.category_name && <span className="shrink-0 rounded-full bg-sunken px-2 py-0.5 text-xs font-semibold text-muted">{categoryLabel(it.category_name)}</span>}
              {it.charged && <span className="shrink-0 text-xs text-positive">חויב</span>}
            </div>
            {it.account_label && (
              <div className="text-xs text-muted">
                {it.charged ? (income ? "נכנס ל" : "ירד מ") : income ? "צפוי להיכנס ל" : "צפוי לרדת מ"}: {it.account_label}
                {it.previous_account_label && (
                  <span className="text-brand">
                    {" "}· עבר מ{it.previous_account_label} ל{it.account_label}
                  </span>
                )}
              </div>
            )}
            <div className="text-xs text-muted">
              <span dir="ltr">{formatDate(it.date)}</span> · {it.basis}
            </div>
          </div>
          <Amount value={it.amount} plain />
        </li>
      ))}
    </ul>
  );
}
