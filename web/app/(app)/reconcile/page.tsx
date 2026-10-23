"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Status } from "@/components/Card";
import type { Reconcile } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export default function ReconcileCurrent() {
  const router = useRouter();
  const { data, error } = useApi<Reconcile>("/reconcile/current");
  useEffect(() => {
    if (data) router.replace(`/reconcile/${data.cycle.label_year}/${data.cycle.label_month}`);
  }, [data, router]);
  return <Status loading error={error} />;
}
