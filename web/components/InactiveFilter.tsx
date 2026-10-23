"use client";

import { useState } from "react";
import type { AccountBrief } from "@/lib/api";

/** Hides inactive cards (no charge in 6 months, no balance) behind a "N לא פעילים" toggle. */
export function useInactive<T extends { active: boolean }>(items: T[] | null) {
  const [show, setShow] = useState(false);
  const hidden = items?.filter((i) => !i.active).length ?? 0;
  const shown = show || !items ? items : items.filter((i) => i.active);
  const toggle =
    hidden > 0 ? (
      <button type="button" className="self-start text-xs font-semibold text-brand" onClick={() => setShow((s) => !s)}>
        {show ? "הסתרת כרטיסים לא פעילים" : `+ ${hidden} כרטיסים לא פעילים`}
      </button>
    ) : null;
  return { shown, toggle };
}

const KINDS = { bank: "חשבון בנק", card: "כרטיס אשראי", fund: "קופה" };

/** The accounts/cards under one connection. */
export function AccountBriefs({ accounts, kinds = false }: { accounts: AccountBrief[]; kinds?: boolean }) {
  const { shown, toggle } = useInactive(accounts);
  if (!accounts.length) return null;
  return (
    <div className="flex flex-col gap-1.5">
      {shown!.length > 0 && (
        <ul className="flex flex-col divide-y divide-hairline rounded-xl bg-bg px-3 text-sm">
          {shown!.map((a) => (
            <li key={a.label} className={`flex items-center justify-between gap-3 py-2 ${a.active ? "" : "text-muted"}`}>
              <span className="truncate font-semibold">{a.label}</span>
              <span className="shrink-0 text-xs text-muted">
                {a.holder}
                {kinds && ` · ${KINDS[a.kind]}`}
              </span>
            </li>
          ))}
        </ul>
      )}
      {toggle}
    </div>
  );
}
