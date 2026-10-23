"use client";

import { useEffect, useState } from "react";
import { send, type Transaction } from "@/lib/api";
import { CategorySelect, loadCategories } from "./CategorySelect";

/** Bottom-sheet to recategorize one transaction (and remember the merchant). */
export function CategoryPicker({
  txn,
  onClose,
  onSaved,
}: {
  txn: Transaction;
  onClose: () => void;
  onSaved: (categoryId: number, categoryName: string, applyToPast: boolean) => void;
}) {
  const [categoryId, setCategoryId] = useState<number | null>(txn.category_id);
  const [applyToPast, setApplyToPast] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (categoryId == null) return;
    setBusy(true);
    try {
      await send("PUT", `/transactions/${txn.id}/category`, { category_id: categoryId, remember: true, apply_to_past: applyToPast });
      const cats = await loadCategories().catch(() => []);
      // Unknown name (fetch failed): keep the old name only if the category didn't change.
      const name = cats.find((c) => c.id === categoryId)?.name ?? (categoryId === txn.category_id ? (txn.category_name ?? "") : "");
      onSaved(categoryId, name, applyToPast);
    } catch {
      setError(true);
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-(--backdrop) p-4 sm:items-center" role="dialog" aria-modal="true" aria-labelledby="pick-title" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <form onSubmit={save} className="card flex w-full max-w-sm flex-col gap-3 rounded-3xl p-5">
        <h2 id="pick-title" className="section-title">
          קטגוריה עבור <span className="font-normal">{txn.description}</span>
        </h2>
        <CategorySelect value={categoryId} onChange={setCategoryId} autoFocus />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={applyToPast} onChange={(e) => setApplyToPast(e.target.checked)} />
          החל גם על עסקאות קודמות
        </label>
        {error && <p className="text-sm text-danger" role="alert">השמירה נכשלה.</p>}
        <div className="flex gap-2">
          <button className="btn flex-1" disabled={busy || categoryId == null}>
            שמירה
          </button>
          <button type="button" className="btn-ghost" onClick={onClose}>
            ביטול
          </button>
        </div>
      </form>
    </div>
  );
}
