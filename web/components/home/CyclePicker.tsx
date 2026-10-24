"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Sheet, SheetTitle } from "@/components/Sheet";
import { formatCycleLabel } from "@/lib/format";

const iso = (y: number, m: number, d: number) => {
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate(); // m is 1-based here
  const t = new Date(Date.UTC(y, m - 1, Math.min(d, last)));
  return t.toISOString().slice(0, 10);
};
const shift = (y: number, m: number, k: number) => {
  const i = y * 12 + (m - 1) + k;
  return [Math.floor(i / 12), (i % 12) + 1] as const;
};

/** Cycles from the current one back a year, mirroring cashflow/cycles.py (fixed start day, clamped to short months). */
export function cycleList(startDay: number, today = new Date(), count = 12) {
  let [y, m] = [today.getFullYear(), today.getMonth() + 1];
  if (iso(y, m, startDay) > iso(y, m, today.getDate())) [y, m] = shift(y, m, -1);
  return Array.from({ length: count }, (_, k) => {
    const [cy, cm] = shift(y, m, -k);
    const [ny, nm] = shift(cy, cm, 1);
    const end = new Date(Date.parse(iso(ny, nm, startDay)) - 86_400_000).toISOString().slice(0, 10);
    return {
      year: cy,
      month: cm,
      label: formatCycleLabel(iso(cy, cm, startDay), end),
      href: k === 0 ? "/home" : `/home/${cy}/${cm}`,
    };
  });
}

/** "בחירת חודש התזרים": radio list of cycles + "הצגה". */
export function CyclePicker({ start, year, month, onClose }: { start: string; year: number; month: number; onClose: () => void }) {
  // ponytail: start day read off the viewed cycle; a clamped one (e.g. 31 → 28 in Feb) shifts the list, read it from settings if that matters.
  const list = cycleList(Number(start.slice(8, 10)));
  const [pick, setPick] = useState(list.find((c) => c.year === year && c.month === month)?.href ?? list[0].href);
  const router = useRouter();
  return (
    <Sheet labelledBy="cycle-pick" onClose={onClose} header={<SheetTitle id="cycle-pick" title="בחירת חודש התזרים:" onClose={onClose} />}>
      <form
        className="flex flex-col"
        onSubmit={(e) => {
          e.preventDefault();
          onClose();
          router.push(pick);
        }}
      >
        <fieldset className="flex flex-col divide-y divide-hairline">
          <legend className="sr-only">חודש התזרים</legend>
          {list.map((c) => (
            <label key={c.href} className="flex min-h-12 cursor-pointer items-center gap-3 px-1">
              <input type="radio" name="cycle" className="size-5 accent-(--brand)" checked={pick === c.href} onChange={() => setPick(c.href)} />
              <span>{c.label}</span>
            </label>
          ))}
        </fieldset>
        <button className="btn sticky bottom-0 mt-3 min-h-12">הצגה</button>
      </form>
    </Sheet>
  );
}
