import { Money } from "@/components/Amount";
import { BAND } from "@/lib/insights";
import { cycleGoal, type HomeData } from "@/lib/home";
import { GoalIllustration } from "./illustrations";

/** Finished cycle: did income cover expenses? Illustration, a worded verdict and the numbers. */
export function GoalBanner({ d }: { d: HomeData }) {
  const g = cycleGoal(d);
  return (
    <section
      aria-label="סיכום המחזור"
      className="card flex items-center gap-3 p-3.5"
    >
      <div
        className={`flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-2xl ${BAND[g.met ? "positive" : "warning"]}`}
      >
        <GoalIllustration met={g.met} />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="text-[15px] leading-snug">
          <strong className={g.met ? "text-positive" : "text-danger-strong"}>
            {g.met ? "עמדת ביעד" : "לא עמדת ביעד"}
          </strong>
          <span className="text-[13px] text-muted">
            {g.met ? " · ההכנסות כיסו את ההוצאות" : " · ההוצאות עלו על ההכנסות"}
          </span>
        </p>
        <dl className="grid grid-cols-3 gap-2 text-[13px]">
          <div>
            <dt className="text-muted">הכנסות</dt>
            <dd>
              <Money value={g.income} className="font-bold" />
            </dd>
          </div>
          <div>
            <dt className="text-muted">הוצאות</dt>
            <dd>
              <Money value={g.expenses} className="font-bold" />
            </dd>
          </div>
          <div>
            <dt className="text-muted">{g.met ? "נשאר" : "חסר"}</dt>
            <dd>
              <Money
                value={Math.abs(g.net)}
                className={`font-bold ${g.met ? "text-positive" : "text-danger-strong"}`}
              />
            </dd>
          </div>
        </dl>
        {g.savings > 0 && (
          <p className="text-xs text-muted">
            לא כולל <Money value={g.savings} /> שהועברו לחיסכון
          </p>
        )}
      </div>
    </section>
  );
}
