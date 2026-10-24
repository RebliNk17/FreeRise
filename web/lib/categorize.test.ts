import { expect, test } from "bun:test";
import type { Category } from "./api";
import { merchantPicks, merchantProgress, merchantSummary, pendingCount, pendingLabel, quickGroups, quickPicks, txnsLeft } from "./categorize";

const cat = (id: number, group: Category["group"], sort_order = 0): Category => ({ id, name: `c${id}`, group, sort_order });

test("pendingCount sums merchant counts", () => {
  expect(pendingCount([{ count: 2 }, { count: 3 }])).toBe(5);
  expect(pendingCount([])).toBe(0);
});

test("chip and sheet labels: transactions and merchants, explicitly", () => {
  const list = [{ count: 100 }, { count: 11 }];
  expect(pendingLabel(list)).toBe("111 עסקאות לסיווג · 2 בתי עסק");
  expect(pendingLabel([{ count: 1 }])).toBe("עסקה אחת לסיווג · בית עסק אחד");
  expect(merchantProgress(0, 64)).toBe("בית עסק 1 מתוך 64");
  expect(txnsLeft(111)).toBe("נשארו 111 עסקאות");
  expect(txnsLeft(1)).toBe("נשארה עסקה אחת");
});

test("merchantSummary: monthly charge, installments, else count + range", () => {
  const base = { count: 12, total: -1068, first_date: "2025-11-03", sample_date: "2026-10-03", monthly: null, installment: null };
  // amounts and dates sit in LTR isolates; compare without them
  const plain = (x: Parameters<typeof merchantSummary>[0]) => {
    const s = merchantSummary(x);
    return { ...s, text: s.text.replace(/[⁦⁩]/g, "") };
  };
  expect(plain({ ...base, monthly: { amount: 89, months: 12, since: "2025-11-03" } })).toEqual({ text: "חיוב חודשי · ₪89 · 12 חודשים (מ-11.25)", fixed: true });
  expect(plain({ ...base, installment: { number: 4, total: 6, amount: 233 } })).toEqual({ text: "תשלום 4/6 · ₪233 לחודש", fixed: true });
  expect(plain(base)).toEqual({ text: "12 עסקאות · ₪1,068 · 03.11.25–03.10.26", fixed: false });
  expect(plain({ ...base, count: 1, first_date: base.sample_date }).text).toBe("עסקה אחת · ₪1,068 · 03.10.26");
  expect(merchantSummary(base).text).toContain("⁦₪1,068⁩");
});

test("merchantPicks: fixed categories first for a likely fixed charge", () => {
  const cats = [cat(1, "variable", 0), cat(2, "variable", 1), cat(3, "fixed", 0), cat(4, "fixed", 1), cat(5, "savings")];
  expect(merchantPicks(cats, [1, 2], -89, false, 4).map((c) => c.id)).toEqual([1, 2, 3, 5]);
  expect(merchantPicks(cats, [1, 2], -89, true, 4).map((c) => c.id)).toEqual([3, 4, 1, 2]);
});

test("quickPicks: most used first, then sort order, filtered by group", () => {
  const cats = [cat(1, "variable", 2), cat(2, "variable", 1), cat(3, "fixed", 0), cat(4, "transfer"), cat(5, "variable", 0)];
  expect(quickPicks(cats, [3, 1], ["variable", "fixed"]).map((c) => c.id)).toEqual([3, 1, 5, 2]);
  expect(quickPicks(cats, [4], ["variable"], 2).map((c) => c.id)).toEqual([5, 2]);
});

test("quickGroups offers income only for credits", () => {
  expect(quickGroups(100)).toContain("income");
  expect(quickGroups(-100)).not.toContain("income");
});
