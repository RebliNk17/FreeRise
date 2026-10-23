"use client";

import { useState } from "react";
import { Amount } from "@/components/Amount";
import { Status, EmptyState } from "@/components/Card";
import { CategorySelect } from "@/components/CategorySelect";
import { Switch } from "@/components/Switch";
import { send, type Uncategorized } from "@/lib/api";
import { txnCount } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function CategorizePage() {
  const { data, setData, error } = useApi<Uncategorized[]>("/categories/uncategorized");
  const [applyToPast, setApplyToPast] = useState(true);
  const [msg, setMsg] = useState("");

  async function assign(u: Uncategorized, category_id: number) {
    setData((d) => d?.filter((x) => x.merchant_key !== u.merchant_key));
    try {
      const { changed } = await send<{ changed: number }>("PUT", "/categories/merchant", { merchant_key: u.merchant_key, category_id, apply_to_past: applyToPast });
      setMsg(`סווגו ${changed} עסקאות.`);
    } catch {
      setData((d) => (d ? [u, ...d] : d));
      setMsg("הסיווג נכשל.");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="page-title">סיווג</h1>
      <Switch checked={applyToPast} onChange={setApplyToPast} label="החל גם על עסקאות קודמות" />
      {msg && <p className="text-sm text-muted" role="status">{msg}</p>}
      <Status loading={!data} error={error} />
      {data?.length === 0 && <EmptyState text="כל העסקאות מסווגות." />}
      <ul className="flex flex-col gap-3">
        {data?.map((u) => (
          <li key={u.merchant_key} className="card flex flex-col gap-2 p-4">
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <div className="truncate font-bold">{u.sample_description}</div>
                <div className="text-xs text-muted">
                  {txnCount(u.count)} · {u.kind === "card" ? "כרטיס אשראי" : "בנק"}
                </div>
              </div>
              <Amount value={u.total} />
            </div>
            <CategorySelect value={null} onChange={(id) => assign(u, id)} label={`קטגוריה עבור ${u.sample_description}`} />
          </li>
        ))}
      </ul>
    </div>
  );
}
