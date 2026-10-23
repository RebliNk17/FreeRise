"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, GripVertical } from "lucide-react";
import { Status } from "@/components/Card";
import { send } from "@/lib/api";
import { categoryLabel } from "@/lib/format";
import type { HomeData } from "@/lib/home";
import { moveItem } from "@/lib/reorder";
import { useApi } from "@/lib/useApi";

type Item = { category_id: number; name: string };

/** Order of the tracked categories on home: drag, or the up/down buttons; saved on every move. */
export default function CategoryOrderPage() {
  const { data, error } = useApi<HomeData>("/home/current");
  const [items, setItems] = useState<Item[] | null>(null);
  const [msg, setMsg] = useState("");
  const [drag, setDrag] = useState<number | null>(null);
  const list = items ?? data?.tracked.map(({ category_id, name }) => ({ category_id, name })) ?? null;

  async function save(next: Item[]) {
    const prev = list;
    setItems(next);
    try {
      await send("PUT", "/tracking/order", { category_ids: next.map((x) => x.category_id) });
      setMsg("הסדר נשמר.");
    } catch {
      setItems(prev);
      setMsg("השמירה נכשלה.");
    }
  }

  async function reset() {
    try {
      await send("DELETE", "/tracking/order");
      setItems(null);
      setMsg("חזרנו לסדר אוטומטי: הגדולות קודם.");
    } catch {
      setMsg("השמירה נכשלה.");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="page-title">סדר הקטגוריות בבית</h1>
      <p className="text-sm text-muted">גוררים או משתמשים בחצים. הסדר נשמר מיד ומשפיע על הקטגוריות במעקב במסך הבית.</p>
      <Status loading={!list} error={error} />
      {list?.length === 0 && <p className="text-muted">אין קטגוריות במעקב.</p>}
      {list && list.length > 0 && (
        <ol className="card flex flex-col divide-y divide-hairline overflow-hidden" aria-label="קטגוריות במעקב">
          {list.map((c, i) => (
            <li
              key={c.category_id}
              draggable
              onDragStart={() => setDrag(i)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => drag != null && drag !== i && save(moveItem(list, drag, i - drag))}
              onDragEnd={() => setDrag(null)}
              className={`flex min-h-14 items-center gap-2 px-3 py-1.5 ${drag === i ? "opacity-50" : ""}`}
            >
              <GripVertical size={18} className="shrink-0 cursor-grab text-faint" aria-hidden />
              <span className="w-6 text-center text-sm text-muted tabular-nums">{i + 1}</span>
              <span className="min-w-0 flex-1 truncate font-semibold">{categoryLabel(c.name)}</span>
              <button type="button" className="icon-btn size-11" aria-label={`הזזת ${categoryLabel(c.name)} למעלה`} disabled={i === 0} onClick={() => save(moveItem(list, i, -1))}>
                <ChevronUp size={18} />
              </button>
              <button type="button" className="icon-btn size-11" aria-label={`הזזת ${categoryLabel(c.name)} למטה`} disabled={i === list.length - 1} onClick={() => save(moveItem(list, i, 1))}>
                <ChevronDown size={18} />
              </button>
            </li>
          ))}
        </ol>
      )}
      {msg && (
        <p className="text-sm text-muted" role="status">
          {msg}
        </p>
      )}
      <button type="button" className="btn-secondary self-start" onClick={reset}>
        חזרה לסדר אוטומטי
      </button>
    </div>
  );
}
