"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Status } from "@/components/Card";
import type { CashFlow } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export default function CashFlowCurrent() {
  const router = useRouter();
  const { data, error } = useApi<CashFlow>("/cashflow/current");
  useEffect(() => {
    if (data) router.replace(`/cashflow/${data.cycle.label_year}/${data.cycle.label_month}`);
  }, [data, router]);
  return <Status loading error={error} />;
}
