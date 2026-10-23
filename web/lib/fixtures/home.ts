// Typed sample of GET /api/home/... — used only in tests.
import type { HomeData, Txn } from "../home";

const txn = (id: number, amount: number, description: string, extra: Partial<Txn> = {}): Txn => ({
  id,
  date: "2026-10-12",
  amount,
  description,
  merchant_key: description,
  category_id: 5,
  category_name: "כלכלה",
  group: "variable",
  account_id: 1,
  account_label: "כרטיס ••7282",
  note: null,
  installment_number: null,
  installment_total: null,
  status: "completed",
  account_holder: "שי",
  cycle_shift: null,
  cycle_label: null,
  fixed_income_id: null,
  cycle_date_source: null,
  ...extra,
});

export const homeFixture: HomeData = {
  cycle: { start: "2026-10-10", end: "2026-11-09", label_year: 2026, label_month: 10, is_current: true, prev: { year: 2026, month: 9 }, next: null },
  summary: { week_left: 812.4, next_week_allowance: 1200, goal: 3000, goal_personal: 2000, goal_plans: 1000, variable_allowance: 5200 },
  variable: {
    spent: 1819.2,
    allowance: 5200,
    weeks: [
      { index: 0, start: "2026-10-10", end: "2026-10-16", spent: 1819.2, left: -119.2, expected: null, is_current: false, is_past: true, transactions: [txn(1, -1819.2, "שופרסל")] },
      { index: 1, start: "2026-10-17", end: "2026-10-23", spent: 0, left: 1200, expected: null, is_current: true, is_past: false, transactions: [] },
    ],
  },
  tracked: [
    {
      category_id: 5,
      name: "כלכלה",
      spent: 1819.2,
      expected: 2400,
      expected_overridden: false,
      left: 580.8,
      mode: "weekly",
      weeks: [{ index: 0, start: "2026-10-10", end: "2026-10-16", spent: 1819.2, left: -1219.2, expected: 600, is_current: true, is_past: false, transactions: [txn(1, -1819.2, "שופרסל")] }],
      transactions: [txn(1, -1819.2, "שופרסל")],
      history: [{ label_year: 2026, label_month: 9, spent: 2300 }],
    },
  ],
  untracked_available: [{ category_id: 7, name: "מסעדות" }],
  savings: { spent: 500, expected: 1000, transactions: [txn(2, -500, "הפקדה", { group: "savings", category_id: 9, category_name: "השקעה וחיסכון" })] },
  fixed: {
    spent: 120,
    expected: 3620,
    groups: [
      {
        category_id: 3,
        name: "דיור",
        spent: 120,
        expected: 3620,
        items: [
          { label: "ועד בית", account_label: "עו״ש ••8901", expected_date: "2026-10-11", expected_amount: 120, actual_amount: 120, status: "charged", transactions: [txn(3, -120, "ועד בית", { group: "fixed" })], recurring_id: 1 },
          { label: "שכירות", account_label: "עו״ש ••8901", expected_date: "2026-10-15", expected_amount: 3500, actual_amount: 0, status: "overdue", transactions: [], recurring_id: 2 },
        ],
      },
    ],
  },
  total: { spent: 2439.2, expected: 9820 },
  income: { received: 0, expected: 14000, fixed_groups: [], variable: { received: 0, transactions: [] } },
  multi_holder: false,
  moved_next: { transactions: [] },
};
