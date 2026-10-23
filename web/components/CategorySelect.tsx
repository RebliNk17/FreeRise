"use client";

import { useEffect, useState } from "react";
import { api, type Category, type Group } from "@/lib/api";
import { categoryLabel } from "@/lib/format";
import { Select } from "@/components/ui/Select";

export const GROUP_LABEL: Record<Group, string> = {
  variable: "הוצאות משתנות",
  fixed: "הוצאות קבועות",
  savings: "הפקדות לחיסכון",
  income: "הכנסות",
  transfer: "העברות",
  card_bill: "חיוב כרטיס אשראי",
  ignore: "התעלמות",
};

// ponytail: module-level cache, categories rarely change within a session.
let cache: Promise<Category[]> | null = null;
export const loadCategories = () => (cache ??= api<Category[]>("/categories").catch((e) => ((cache = null), Promise.reject(e))));

export function CategorySelect({
  value,
  onChange,
  className,
  label = "קטגוריה",
  autoFocus,
  groups = Object.keys(GROUP_LABEL) as Group[],
  exclude,
}: {
  value: number | null;
  onChange: (id: number) => void;
  className?: string;
  label?: string;
  autoFocus?: boolean;
  /** Only these groups (e.g. the other one for "this isn't a fixed expense"). */
  groups?: Group[];
  exclude?: number | null;
}) {
  const [cats, setCats] = useState<Category[]>([]);
  useEffect(() => {
    loadCategories().then(setCats, () => {});
  }, []);
  const options = groups.flatMap((g) =>
    cats
      .filter((c) => c.group === g && c.id !== exclude)
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((c) => ({ value: String(c.id), label: categoryLabel(c.name), group: GROUP_LABEL[g] })),
  );
  return (
    <Select
      autoFocus={autoFocus}
      className={className}
      label={label}
      placeholder="בחירת קטגוריה…"
      value={value == null ? "" : String(value)}
      onChange={(v) => onChange(Number(v))}
      options={options}
    />
  );
}
