"use client";

import { useState } from "react";
import { CalendarX, Pencil, Repeat, Undo2 } from "lucide-react";
import { Money } from "@/components/Amount";
import { Sheet, SheetTitle } from "@/components/Sheet";
import { send } from "@/lib/api";
import { formatDate, formatILS } from "@/lib/format";
import type { FixedItem } from "@/lib/home";
import { useHome } from "./context";
import { ActionList, type Action } from "./TxnSheet";

/** An expected fixed expense / income that hasn't come yet: change what's expected (this month
 * only, or from now on), say it won't come this month, or that it isn't fixed at all. */
export function ExpectedSheet({ it, income, onClose }: { it: FixedItem & { recurring_id: number }; income: boolean; onClose: () => void }) {
  const { mutate } = useHome();
  const [editing, setEditing] = useState(false);
  const id = it.recurring_id;

  function request(req: () => Promise<unknown>) {
    onClose();
    mutate((d) => d, req); // the home refetch shows the new expectation
  }

  const actions: Action[] = [{ icon: <Pencil size={18} />, label: "שינוי הסכום הצפוי", value: formatILS(it.expected_amount), run: () => setEditing(true) }];
  if (it.overridden) actions.push({ icon: <Undo2 size={18} />, label: "חזרה לסכום הרגיל", run: () => request(() => send("DELETE", `/recurring/${id}/skip`)) });
  actions.push(
    { icon: <CalendarX size={18} />, label: income ? "לא נכנסת החודש" : "לא יורדת החודש", tone: "sun", run: () => request(() => send("POST", `/recurring/${id}/skip`, {})) },
    {
      icon: <Repeat size={18} />,
      label: income ? "זו לא הכנסה קבועה" : "זו לא הוצאה קבועה",
      tone: "danger",
      run: () => request(() => (income ? send("DELETE", `/recurring/${id}/fixed`) : send("PUT", `/recurring/${id}`, { status: "dismissed" }))),
    },
  );

  return (
    <Sheet
      labelledBy="expected-title"
      onClose={onClose}
      form={editing}
      header={
        <>
          <SheetTitle id="expected-title" title={it.label} onClose={onClose} />
          <p className="-mt-2 text-[13px] text-muted">
            {income ? "צפויה להיכנס" : "צפויה לרדת"} <Money value={it.expected_amount} className="font-semibold text-text" />
            {it.expected_date && (
              <>
                {" "}
                ב־<span dir="ltr">{formatDate(it.expected_date)}</span>
              </>
            )}
            {it.account_label && ` · ${it.account_label}`}
            {it.overridden && " · עודכן לחודש הזה"}
          </p>
        </>
      }
    >
      {editing ? (
        <AmountForm
          initial={it.expected_amount}
          onCancel={() => setEditing(false)}
          onSave={(amount, scope) => request(() => send("PUT", `/recurring/${id}/expected`, { amount, scope }))}
        />
      ) : (
        <ActionList items={actions} />
      )}
    </Sheet>
  );
}

function AmountForm({ initial, onSave, onCancel }: { initial: number; onSave: (amount: number, scope: "cycle" | "forward") => void; onCancel: () => void }) {
  const [value, setValue] = useState(String(initial));
  const amount = Number(value);
  const ok = value.trim() !== "" && Number.isFinite(amount) && amount > 0;
  return (
    <form className="card flex flex-col gap-3 p-3.5" onSubmit={(e) => e.preventDefault()}>
      <label className="flex flex-col gap-1 text-sm font-semibold">
        סכום צפוי
        <input className="input" dir="ltr" type="number" inputMode="decimal" min={0} step="any" value={value} onChange={(e) => setValue(e.target.value)} autoFocus onFocus={(e) => e.target.select()} />
      </label>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn flex-1" disabled={!ok} onClick={() => onSave(amount, "cycle")}>
          רק החודש
        </button>
        <button type="button" className="btn flex-1" disabled={!ok} onClick={() => onSave(amount, "forward")}>
          מעכשיו והלאה
        </button>
      </div>
      <button type="button" className="btn-ghost" onClick={onCancel}>
        ביטול
      </button>
    </form>
  );
}
