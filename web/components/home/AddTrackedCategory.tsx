"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { send } from "@/lib/api";
import { categoryLabel } from "@/lib/format";
import { Select } from "@/components/ui/Select";
import { useHome } from "./context";

/** "+ הוספת קטגוריה למעקב": picker of variable categories not tracked yet. */
export function AddTrackedCategory() {
  const { data, mutate } = useHome();
  const [open, setOpen] = useState(false);
  const [id, setId] = useState("");
  if (!data.untracked_available.length) return null;
  if (!open)
    return (
      <button type="button" className="flex min-h-12 items-center justify-center gap-1.5 rounded-[20px] border-2 border-dashed border-border py-3 text-sm font-bold text-brand hover:border-brand" onClick={() => setOpen(true)}>
        <Plus size={16} /> הוספת קטגוריה למעקב
      </button>
    );
  return (
    <form
      className="card flex flex-wrap gap-2 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        const cid = Number(id);
        if (!cid) return;
        setOpen(false);
        setId("");
        mutate((d) => ({ ...d, untracked_available: d.untracked_available.filter((c) => c.category_id !== cid) }), () => send("PUT", `/tracking/${cid}`, { tracked: true }));
      }}
    >
      <Select
        className="min-w-0 flex-1"
        label="קטגוריה למעקב"
        placeholder="בחירת קטגוריה…"
        value={id}
        onChange={setId}
        options={data.untracked_available.map((c) => ({ value: String(c.category_id), label: categoryLabel(c.name) }))}
        autoFocus
      />
      <button className="btn" disabled={!id}>
        הוספה
      </button>
      <button type="button" className="btn-ghost" onClick={() => setOpen(false)}>
        ביטול
      </button>
    </form>
  );
}
