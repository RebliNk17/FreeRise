import { Card } from "@/components/Card";
import type { HomeData } from "@/lib/home";
import { Expander } from "./Expander";
import { HistoryButton } from "./HistorySheet";
import { FixedGroups } from "./FixedCard";
import { SpentHeader } from "./parts";
import { TxnList } from "./TxnRow";

export function IncomeCard({ inc }: { inc: HomeData["income"] }) {
  return (
    <Card title="הכנסות" action={<HistoryButton kind="income" title="הכנסות" labels={["נכנס", "צפוי"]} />}>
      <SpentHeader spent={inc.received} expected={inc.expected} labels={["נכנס", "צפוי להיכנס"]} remaining={["עוד צפוי להיכנס", "נכנס מעבר לצפוי"]} overIsBad={false} />
      {inc.fixed_groups.length > 0 && (
        <Expander label={<span className="text-sm font-semibold text-brand">פירוט הכנסות קבועות</span>} className="border-t border-hairline pt-1.5" buttonClassName="flex min-h-11 px-1">
          <div className="pt-2">
            <FixedGroups groups={inc.fixed_groups} income />
          </div>
        </Expander>
      )}
      <Expander label={<span className="text-sm font-semibold text-brand">פירוט הכנסות משתנות</span>} className="border-t border-hairline pt-1.5" buttonClassName="flex min-h-11 px-1">
        <div className="pt-2">
          <TxnList txns={inc.variable.transactions} empty="אין הכנסות משתנות במחזור הזה" />
        </div>
      </Expander>
    </Card>
  );
}
