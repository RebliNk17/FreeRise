"use client";

import { createContext, useContext } from "react";
import type { HomeData, Txn } from "@/lib/home";

export type HomeCtx = {
  data: HomeData;
  /** Apply `optimistic` now, run `request`; on failure roll back. Always refetches. Resolves to success. */
  mutate: (optimistic: (d: HomeData) => HomeData, request: () => Promise<unknown>) => Promise<boolean>;
  openTxn: (t: Txn) => void;
  /** Bumped after every mutation; side cards pass it to useApi to refetch alongside /api/home. */
  version: number;
};

export const HomeContext = createContext<HomeCtx | null>(null);
export const useHome = () => useContext(HomeContext)!;
