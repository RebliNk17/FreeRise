import { Card } from "@/components/Card";
import type { HomeData } from "@/lib/home";
import { Expander } from "./Expander";
import { HistoryButton } from "./HistorySheet";
import { SpentHeader } from "./parts";
import { TxnList } from "./TxnRow";

export function SavingsCard({ s }: { s: HomeData["savings"] }) {
  if (!s.expected && !s.transactions.length) return null;
  return (
    <Card title="הפקדות לחיסכון" action={<HistoryButton kind="savings" title="הפקדות לחיסכון" labels={["הופקד", "צפוי"]} />}>
      <SpentHeader spent={s.spent} expected={s.expected} labels={["הופקד", "צפוי להיות מופקד"]} remaining={["נשאר להפקיד", "הופקד מעבר לצפוי"]} overIsBad={false} />
      <Expander label={<span className="text-sm font-semibold text-brand">פירוט הפקדות</span>} className="border-t border-hairline pt-1.5" buttonClassName="flex min-h-11 px-1">
        <div className="pt-2">
          <TxnList txns={s.transactions} empty="עוד לא הופקד במחזור הזה" />
        </div>
      </Expander>
    </Card>
  );
}
