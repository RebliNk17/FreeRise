import { Money } from "@/components/Amount";
import { Card } from "@/components/Card";
import { categoryLabel, formatDate } from "@/lib/format";
import { FIXED_STATUS, installmentLabel, type FixedGroup, type FixedItem, type HomeData } from "@/lib/home";
import { Expander } from "./Expander";
import { HistoryButton } from "./HistorySheet";
import { SpentHeader, TableHead } from "./parts";
import { TxnList } from "./TxnRow";

export function FixedCard({ f }: { f: HomeData["fixed"] }) {
  return (
    <Card title="הוצאות קבועות" action={<HistoryButton kind="fixed" title="הוצאות קבועות" />}>
      <SpentHeader spent={f.spent} expected={f.expected} />
      {f.groups.length > 0 && (
        <Expander label={<span className="text-sm font-semibold text-brand">פירוט חודשי</span>} buttonClassName="flex min-h-11 border-t border-hairline pt-2">
          <div className="pt-2">
            <FixedGroups groups={f.groups} />
          </div>
        </Expander>
      )}
    </Card>
  );
}

const INCOME_STATUS: Record<FixedItem["status"], string> = { charged: "נכנס", expected: "צפוי", overdue: "לא נכנס עדיין" };

/** Category rows (קטגוריה · יצא · צפוי) expanding to items; items with transactions expand again. */
export function FixedGroups({ groups, income = false }: { groups: FixedGroup[]; income?: boolean }) {
  return (
    <div>
      <TableHead cols={["קטגוריה", income ? "נכנס" : "יצא", income ? "צפוי להיכנס" : "צפוי לצאת"]} />
      <ul className="flex flex-col divide-y divide-hairline">
        {groups.map((g) => (
          <li key={g.category_id ?? g.name}>
            <Expander
              buttonClassName="grid min-h-12 grid-cols-[1fr_5rem_5rem_18px] rounded-xl px-1 py-2.5 hover:bg-sunken/50"
              labelClassName="contents"
              label={
                <>
                  <span className="truncate text-sm font-bold">{categoryLabel(g.name)}</span>
                  <Money value={g.spent} className="justify-self-end text-sm font-bold" />
                  <Money value={g.expected} className="justify-self-end text-sm text-muted" />
                </>
              }
            >
              <ul className="mb-2 flex flex-col gap-1 rounded-2xl bg-bg p-1.5">
                {g.items.map((it, i) => (
                  <li key={it.recurring_id ?? `${it.label}-${i}`}>
                    <Item it={it} income={income} />
                  </li>
                ))}
              </ul>
            </Expander>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Item({ it, income }: { it: FixedItem; income: boolean }) {
  const date = it.transactions[0]?.date ?? it.expected_date;
  const st = FIXED_STATUS[it.status];
  const inst = installmentLabel(it);
  const body = (
    <span className="flex items-start gap-3">
      <span className="block min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="truncate text-sm font-semibold">{it.label}</span>
          <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold ${st.tone}`}>{income ? INCOME_STATUS[it.status] : st.label}</span>
        </span>
        <span className="block text-xs text-muted">
          {inst && <span className="font-semibold text-text">{inst} · </span>}
          {date && <span dir="ltr">{formatDate(date)}</span>}
          {it.account_label && ` · ${it.account_label}`}
        </span>
      </span>
      <span className="flex shrink-0 flex-col items-end">
        <Money value={it.actual_amount} className="text-sm font-bold" />
        <span className="text-[11px] text-muted">
          מתוך <Money value={it.expected_amount} />
        </span>
      </span>
    </span>
  );
  const box = `rounded-xl px-2 py-2 ${it.status === "expected" ? "opacity-60" : ""} ${it.status === "overdue" ? "bg-sun-soft" : ""}`;
  if (!it.transactions.length) return <div className={box}>{body}</div>;
  return (
    <Expander className={box} label={body}>
      <div className="pt-1">
        <TxnList txns={it.transactions} />
      </div>
    </Expander>
  );
}
