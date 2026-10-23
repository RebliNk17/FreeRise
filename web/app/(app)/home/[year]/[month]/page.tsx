"use client";

import { useParams } from "next/navigation";
import { HomeView } from "@/components/home/HomeView";
import { monthName } from "@/lib/format";

export default function HomeCycle() {
  const { year, month } = useParams<{ year: string; month: string }>();
  return <HomeView path={`/home/${Number(year)}/${Number(month)}`} title={`${monthName(Number(month))} ${year}`} />;
}
