"use client";

import { useState } from "react";
import { SlidersHorizontal, X } from "lucide-react";
import { Sheet, SheetTitle } from "@/components/Sheet";
import type { Account } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { holderChoices, setHidden, useHiddenAccounts } from "@/lib/viewFilter";

const KIND: Record<Account["kind"], string> = { bank: "עו״ש", card: "כרטיס אשראי", fund: "קרן" };

/** Under the cycle switcher: "חשבונות להצגה" button, or a clear indicator while some accounts are hidden. */
export function AccountFilter() {
  const hidden = useHiddenAccounts();
  const { data } = useApi<Account[]>("/accounts");
  const [open, setOpen] = useState(false);
  // Excluded accounts never count anyway; inactive cards are noise in the picker.
  const accounts = (data ?? []).filter((a) => !a.excluded && a.kind !== "fund" && (a.active || hidden.includes(a.id)));
  const hiddenHere = accounts.filter((a) => hidden.includes(a.id)).length;
  if (accounts.length < 2 && !hiddenHere) return null;

  return (
    <>
      {hiddenHere > 0 ? (
        <div className="flex items-center gap-2 rounded-2xl bg-sun-soft px-3 py-1.5 text-sm" role="status">
          <SlidersHorizontal size={16} className="shrink-0 text-sun-strong" aria-hidden />
          <button type="button" className="min-h-11 flex-1 text-start font-semibold" onClick={() => setOpen(true)}>
            מוצגים {accounts.length - hiddenHere} מתוך {accounts.length} חשבונות
          </button>
          <button type="button" className="btn-ghost min-h-11 bg-transparent" onClick={() => setHidden([])}>
            <X size={14} aria-hidden /> הצגת הכל
          </button>
        </div>
      ) : (
        <button type="button" className="link flex min-h-11 items-center gap-1.5 self-center px-2" onClick={() => setOpen(true)}>
          <SlidersHorizontal size={15} aria-hidden /> חשבונות להצגה
        </button>
      )}
      {open && <AccountSheet accounts={accounts} hidden={hidden} onClose={() => setOpen(false)} />}
    </>
  );
}

function AccountSheet({ accounts, hidden, onClose }: { accounts: Account[]; hidden: number[]; onClose: () => void }) {
  const choices = holderChoices(accounts);
  const toggle = (id: number, show: boolean) => setHidden(show ? hidden.filter((x) => x !== id) : [...hidden, id]);
  const same = (ids: number[]) => ids.length === hidden.length && ids.every((x) => hidden.includes(x));
  return (
    <Sheet labelledBy="acct-filter-title" onClose={onClose} header={<SheetTitle id="acct-filter-title" title="חשבונות להצגה" onClose={onClose} />}>
      <div className="flex flex-col gap-3">
        <p className="text-sm text-muted">בחירה זמנית לתצוגה בבית ובתזרים, נשמרת רק בדפדפן הזה. להחרגה קבועה יש מסך חשבונות.</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" aria-pressed={hidden.length === 0} className={`chip min-h-11 px-4 text-sm ${hidden.length === 0 ? "bg-brand-fill text-brand-fg" : "bg-sunken text-text"}`} onClick={() => setHidden([])}>
            כל החשבונות
          </button>
          {choices.map((c) => (
            <button key={c.holder} type="button" aria-pressed={same(c.hide)} className={`chip min-h-11 px-4 text-sm ${same(c.hide) ? "bg-brand-fill text-brand-fg" : "bg-sunken text-text"}`} onClick={() => setHidden(c.hide)}>
              רק של {c.holder}
            </button>
          ))}
        </div>
        <ul className="card flex flex-col divide-y divide-hairline overflow-hidden">
          {accounts.map((a) => (
            <li key={a.id}>
              <label className="flex min-h-14 cursor-pointer items-center gap-3 px-4 py-2.5">
                <input type="checkbox" checked={!hidden.includes(a.id)} onChange={(e) => toggle(a.id, e.target.checked)} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold">{a.label}</span>
                  <span className="block text-xs text-muted">
                    {KIND[a.kind]}
                    {a.holder && ` · ${a.holder}`}
                  </span>
                </span>
              </label>
            </li>
          ))}
        </ul>
        <button type="button" className="btn" onClick={onClose}>
          סיום
        </button>
      </div>
    </Sheet>
  );
}
