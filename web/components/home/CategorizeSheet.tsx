"use client";

import { createElement, useEffect, useState } from "react";
import { Check, ChevronLeft, SkipForward, Tags } from "lucide-react";
import { Money } from "@/components/Amount";
import { categoryIcon } from "@/components/CategoryIcon";
import { CategorySelect, loadCategories } from "@/components/CategorySelect";
import { Sheet, SheetTitle } from "@/components/Sheet";
import { Switch } from "@/components/Switch";
import { api, send, type Category, type Uncategorized } from "@/lib/api";
import { merchantProgress, pendingCount, pendingLabel, quickGroups, quickPicks, txnsLeft } from "@/lib/categorize";
import { categoryLabel, formatDate, txnCount } from "@/lib/format";

/** Home chip "N עסקאות לסיווג · M בתי עסק": tap opens the sheet. */
export function CategorizeChip({ list, onOpen }: { list: Uncategorized[]; onOpen: () => void }) {
  if (!pendingCount(list)) return null;
  return (
    <button type="button" onClick={onOpen} className="card flex min-h-12 items-center gap-3 px-4 py-2.5 text-start hover:bg-sunken/60">
      <span className="flex size-[34px] shrink-0 items-center justify-center rounded-[11px] bg-sun-soft text-sun-strong">
        <Tags size={18} aria-hidden />
      </span>
      <span className="flex-1 font-bold">{pendingLabel(list)}</span>
      <ChevronLeft size={18} className="text-faint" aria-hidden />
    </button>
  );
}

/** One merchant at a time: quick category buttons (most used first), "עוד קטגוריות", always-like-this toggle, skip. */
export function CategorizeSheet({ list, onClose }: { list: Uncategorized[]; onClose: (changed: boolean) => void }) {
  const [queue] = useState(list); // fixed for the session so the progress count stays honest
  const [i, setI] = useState(0);
  const [cats, setCats] = useState<Category[]>([]);
  const [usage, setUsage] = useState<number[]>([]);
  const [always, setAlways] = useState(true);
  const [more, setMore] = useState(false);
  const [changed, setChanged] = useState(false);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [left, setLeft] = useState(() => pendingCount(list)); // drops as merchants are categorized

  useEffect(() => {
    loadCategories().then(setCats, () => {});
    api<number[]>("/categories/usage").then(setUsage, () => {});
  }, []);

  const u = queue[i];
  const close = () => onClose(changed);
  const next = () => {
    setMore(false);
    setI((x) => x + 1);
  };

  async function assign(category_id: number) {
    if (!u || busy) return;
    setBusy(true);
    setFailed(false);
    try {
      await send("PUT", "/categories/merchant", { merchant_key: u.merchant_key, category_id, apply_to_past: true, remember: always });
      setChanged(true);
      setLeft((n) => n - u.count);
      next();
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  const picks = u ? quickPicks(cats, usage, quickGroups(u.total)) : [];
  return (
    <Sheet
      labelledBy="categorize-title"
      onClose={close}
      header={<SheetTitle id="categorize-title" title="סיווג עסקאות" onClose={close} />}
    >
      {!u ? (
        <div className="card flex flex-col items-center gap-3 p-6 text-center">
          <span className="flex size-14 items-center justify-center rounded-full bg-brand-soft text-brand">
            <Check size={28} aria-hidden />
          </span>
          <p className="font-bold">{queue.length ? "סיימתם לסווג!" : "אין עסקאות לסיווג."}</p>
          <button type="button" className="btn min-w-40" onClick={close}>
            סגירה
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-3.5">
          <p className="text-center text-sm text-muted" aria-live="polite">
            <span className="font-semibold text-text">{merchantProgress(i, queue.length)}</span> · {txnsLeft(left)}
          </p>
          <div className="card flex flex-col gap-1 p-4">
            <h3 className="truncate font-display text-xl font-bold">{u.sample_description}</h3>
            <p className="text-sm text-muted">
              {txnCount(u.count)} · <Money value={Math.abs(u.total)} className="font-bold text-text" />
              {u.total > 0 && " זיכוי"}
            </p>
            <p className="text-xs text-muted">
              לאחרונה <span dir="ltr">{formatDate(u.sample_date)}</span>
              {u.account_label && ` · ${u.account_label}`}
            </p>
          </div>
          <ul className="grid grid-cols-2 gap-2" aria-label="קטגוריות נפוצות">
            {picks.map((c) => (
              <li key={c.id}>
                <button type="button" disabled={busy} className="card flex min-h-14 w-full items-center gap-2.5 px-3 py-2 text-start font-bold hover:bg-sunken/60 disabled:opacity-50" onClick={() => assign(c.id)}>
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-[10px] bg-brand-soft text-brand" aria-hidden>
                    {createElement(categoryIcon(c.name), { size: 16 })}
                  </span>
                  <span className="min-w-0 truncate">{categoryLabel(c.name)}</span>
                </button>
              </li>
            ))}
          </ul>
          {more ? (
            <CategorySelect value={null} onChange={assign} label="כל הקטגוריות" autoFocus />
          ) : (
            <button type="button" className="btn-secondary" onClick={() => setMore(true)}>
              עוד קטגוריות
            </button>
          )}
          <Switch checked={always} onChange={setAlways} label={`תמיד לסווג כך את ${u.sample_description}`} />
          {failed && (
            <p className="text-sm font-semibold text-danger" role="alert">
              השמירה נכשלה, נסו שוב.
            </p>
          )}
          <button type="button" className="btn-ghost" onClick={next} disabled={busy}>
            <SkipForward size={16} aria-hidden /> דילוג
          </button>
        </div>
      )}
    </Sheet>
  );
}
