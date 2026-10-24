"use client";

import { Money } from "@/components/Amount";
import { Card } from "@/components/Card";
import { ExpectedItems } from "@/components/ExpectedItems";
import type { Forecast } from "@/lib/api";
import { formatCycleLabel } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useHome } from "./context";
import { Expander } from "./Expander";

// ponytail: current-state data comes from the existing /forecast/next endpoint
// (current cycle only), so /api/home stays per-cycle.

/** "החודש הבא" (#next): expected fixed charges and income with their dates and accounts,
 * the change from this cycle, and the installments that end this cycle (also an insight slide). */
export function NextCycleCard() {
  const { data: f } = useApi<Forecast>("/forecast/next", useHome().version);
  if (!f) return null;
  return (
    <div id="next" className="scroll-mt-20">
      <Card title="החודש הבא" action={<span className="text-xs text-muted">{formatCycleLabel(f.cycle.start, f.cycle.end)}</span>}>
        <Expander
          buttonClassName="flex min-h-11"
          label={
            <span className="flex items-baseline gap-2 text-sm">
              <span className="flex-1">הוצאות קבועות צפויות</span>
              <Money value={f.fixed_total} className="font-semibold" />
            </span>
          }
        >
          <div className="pb-1">
            {f.delta_fixed_vs_current !== 0 && (
              <p className="text-xs text-muted">
                {f.delta_fixed_vs_current > 0 ? "יותר" : "פחות"} מהחודש הנוכחי ב־<Money value={Math.abs(f.delta_fixed_vs_current)} />
              </p>
            )}
            <ExpectedItems items={f.fixed_items} none="לא זוהו חיובים קבועים." />
          </div>
        </Expander>
        <Expander
          className="border-t border-hairline" buttonClassName="flex min-h-11 px-1"
          label={
            <span className="flex items-baseline gap-2 text-sm">
              <span className="flex-1">הכנסות צפויות</span>
              <Money value={f.income_total} className="font-semibold" />
            </span>
          }
        >
          <div className="pb-1">
            <ExpectedItems income items={f.income_items} none="לא זוהו הכנסות קבועות." />
          </div>
        </Expander>
        {f.installments_stopping.length > 0 ? (
          <Expander
            className="border-t border-hairline" buttonClassName="flex min-h-11 px-1"
            label={
              <span className="flex items-baseline gap-2 text-sm">
                <span className="flex-1">
                  יסתיימו {f.installments_stopping.length} תשלומים החודש
                </span>
                <Money value={f.installments_stopping_total} className="font-semibold text-positive" />
              </span>
            }
          >
            <div className="pb-1">
              <p className="text-xs text-muted">מהחודש הבא הם כבר לא ירדו</p>
              <ExpectedItems items={f.installments_stopping} none="" />
            </div>
          </Expander>
        ) : (
          <p className="border-t border-hairline pt-3 text-sm text-muted">אין תשלומים שמסתיימים החודש.</p>
        )}
      </Card>
    </div>
  );
}
