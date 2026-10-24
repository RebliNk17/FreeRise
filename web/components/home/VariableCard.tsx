import { Card } from "@/components/Card";
import type { HomeData } from "@/lib/home";
import { Expander } from "./Expander";
import { HistoryButton } from "./HistorySheet";
import { SpentHeader } from "./parts";
import { WeekTable } from "./WeekTable";

const TITLE = "שאר ההוצאות המשתנות";

/** Variable spending outside the tracked categories (they have their own cards); its weeks are the weekly allowance. */
export function VariableCard({ v }: { v: HomeData["variable"] }) {
  return (
    <Card title={TITLE} action={<HistoryButton kind="variable" title={TITLE} />}>
      <p className="-mt-2 text-xs text-muted">בלי הקטגוריות במעקב · מכאן התקציב השבועי</p>
      <SpentHeader spent={v.spent} expected={v.allowance} labels={["יצא", "תקציב החודש"]} />
      {v.weeks.length > 0 && (
        <Expander label={<span className="text-sm font-semibold text-brand">פירוט שבועי</span>} className="border-t border-hairline pt-1.5" buttonClassName="flex min-h-11 px-1">
          <div className="pt-2">
            <WeekTable weeks={v.weeks} col="left" />
          </div>
        </Expander>
      )}
    </Card>
  );
}
