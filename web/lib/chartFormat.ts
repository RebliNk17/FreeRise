// Shared chart text helpers (components/charts).

import { splitMoney } from "./home";

/** Bar labels: the exact amount, never rounded (money) - 8645.9 → "8,645.9", -1200 → "-1,200". */
export function chartMoney(n: number): string {
  const { sign, int, dec } = splitMoney(n);
  return `${sign}${int}${dec}`;
}

/** Which bar the caption describes: the picked one, else the newest (last). -1 when empty. */
export const captionIndex = (n: number, picked: number | null) => (picked != null && picked >= 0 && picked < n ? picked : n - 1);
