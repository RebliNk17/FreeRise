import { Card } from "@/components/Card";
import type { HomeData } from "@/lib/home";
import { Expander } from "./Expander";
import { SpentHeader } from "./parts";
import { WeekTable } from "./WeekTable";

export function VariableCard({ v }: { v: HomeData["variable"] }) {
  return (
    <Card>
      <SpentHeader spent={v.spent} expected={v.allowance} labels={["יצא", "תקציב החודש"]} />
      {v.weeks.length > 0 && (
        <Expander label={<span className="text-sm font-semibold text-brand">פירוט שבועי</span>} buttonClassName="flex min-h-11 border-t border-hairline pt-2">
          <div className="pt-2">
            <WeekTable weeks={v.weeks} col="left" />
          </div>
        </Expander>
      )}
    </Card>
  );
}
