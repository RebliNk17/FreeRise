"use client";

import { useState } from "react";
import { Pencil } from "lucide-react";
import { Money } from "@/components/Amount";
import { formatDate } from "@/lib/format";
import { daysLabel, weekDays, weekOver, weekStatus, type Week } from "@/lib/home";
import { Expander } from "./Expander";
import { TableHead } from "./parts";
import { TxnList } from "./TxnRow";

const dm = (iso: string) => formatDate(iso).slice(0, 5);
const ROW = "relative grid grid-cols-[1fr_5rem_5rem_18px] items-center gap-2";

/** Week rows (current week = filled pill, future greyed); each row expands to its transactions.
 * col "left" → נשאר להוציא; "expected" → צפוי לצאת with an optional pencil per week. */
export function WeekTable({ weeks, col, onEdit }: { weeks: Week[]; col: "left" | "expected"; onEdit?: (w: Week, amount: number | null) => void }) {
  return (
    <div>
      <TableHead cols={["שבוע", "יצא", col === "left" ? "נשאר להוציא" : "צפוי לצאת"]} />
      <ul className="flex flex-col divide-y divide-hairline">
        {weeks.map((w) => {
          const st = weekStatus(w);
          const value = col === "left" ? w.left : (w.expected ?? 0);
          const over = weekOver(w);
          return (
            <li key={w.index} className={st === "future" ? "opacity-70" : ""}>
              <Expander
                rowClassName={ROW}
                buttonClassName="col-span-full row-start-1 grid min-h-13 grid-cols-subgrid rounded-xl px-1 py-2.5 hover:bg-sunken/50"
                labelClassName="contents"
                label={
                  <>
                    <span className="flex flex-col items-start gap-0.5">
                      <span className={`rounded-full px-2.5 py-0.5 text-[13px] font-bold whitespace-nowrap ${st === "current" ? "bg-brand-fill text-brand-fg" : "bg-sunken text-text"}`}>
                        שבוע {w.index + 1}
                        {st === "current" && <span className="sr-only"> (השבוע הנוכחי)</span>}
                      </span>
                      <span className="px-2 text-[11px] text-muted">
                        <span dir="ltr">
                          {dm(w.start)}–{dm(w.end)}
                        </span>{" "}
                        · {daysLabel(weekDays(w))}
                      </span>
                    </span>
                    <span className="flex flex-col items-end justify-self-end">
                      <Money value={w.spent} className={`text-sm ${st === "future" ? "" : "font-bold"} ${over ? "text-danger" : ""}`} />
                      {over && <span className="text-[11px] font-semibold text-danger">חריגה</span>}
                    </span>
                    <Money value={value} className={`justify-self-end text-sm ${value < 0 ? "text-danger" : ""}`} />
                  </>
                }
                aside={onEdit && !w.is_past && <WeekEdit w={w} onSave={(a) => onEdit(w, a)} />}
              >
                <div className="px-1 pb-2">
                  <TxnList txns={w.transactions} empty={st === "future" ? "השבוע עוד לא התחיל" : "אין עסקאות בשבוע הזה"} />
                </div>
              </Expander>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function WeekEdit({ w, onSave }: { w: Week; onSave: (amount: number | null) => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  if (!editing)
    return (
      <button
        type="button"
        className="z-[1] col-start-3 row-start-1 flex size-8 items-center justify-center justify-self-start self-center rounded-lg text-muted hover:bg-sunken hover:text-text"
        aria-label={`עריכת הסכום הצפוי לשבוע ${w.index + 1}`}
        onClick={() => {
          setValue(w.expected == null ? "" : String(Math.round(w.expected)));
          setEditing(true);
        }}
      >
        <Pencil size={13} />
      </button>
    );
  return (
    <form
      className="z-[2] col-span-full row-start-1 flex items-center gap-2 bg-surface py-1"
      onSubmit={(e) => {
        e.preventDefault();
        const n = Number(value);
        if (value.trim() === "" || !Number.isFinite(n) || n < 0) return;
        setEditing(false);
        onSave(n);
      }}
    >
      <input type="number" min={0} step="any" inputMode="decimal" dir="ltr" className="input min-h-10 min-w-0 py-1.5" value={value} onChange={(e) => setValue(e.target.value)} aria-label="סכום צפוי לשבוע" autoFocus onFocus={(e) => e.target.select()} />
      <button className="btn min-h-10 px-3 py-1.5 text-sm">שמירה</button>
      <button
        type="button"
        className="btn-ghost px-2 py-1.5 text-xs"
        onClick={() => {
          setEditing(false);
          onSave(null);
        }}
      >
        אוטומטי
      </button>
      <button type="button" className="btn-ghost px-2 py-1.5 text-xs" onClick={() => setEditing(false)}>
        ביטול
      </button>
    </form>
  );
}
