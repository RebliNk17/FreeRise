export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`API ${status}`);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (typeof init?.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`/api${path}`, { ...init, headers, credentials: "include" });
  const text = await res.text();
  let body: unknown = text;
  try {
    body = text ? JSON.parse(text) : undefined;
  } catch {}
  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined" && window.location.pathname !== "/login") {
      // Full reload on purpose: drops all client state of the logged-out session.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.href = "/login";
    }
    throw new ApiError(res.status, body);
  }
  return body as T;
}

/** JSON request helper: send("POST", "/sync", {credential_id: 1}) */
export const send = <T = void>(method: string, path: string, body?: unknown) =>
  api<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

/** A txn attributed to the previous/next cycle (late or early income, or by hand). */
export type CycleShift = "previous" | "next";

// Shapes from the Task 8 API contract. Money comes as string (Decimal) or number.
export type Money = string | number;

export type Provider = {
  key: string;
  name: string;
  service: string;
  required_fields: string[];
  optional_fields: string[];
};

export type Credential = {
  id: number;
  provider: string;
  label: string;
  owner: string;
  enabled: boolean;
  last_success_at: string | null;
  last_error: string | null;
  last_failure_kind: "auth_failed" | "provider_changed" | "timeout" | "otp_timeout" | "other" | null;
  sync_paused: boolean; // scheduled syncs stopped after repeated login failures; a successful sync resumes them
  fields: Record<string, string>;
  accounts: AccountBrief[];
  verify_run_id?: number | null; // set when the request started a connection check
};

/** An account/card under a connection: label is "מקס ••4720". */
export type AccountBrief = { label: string; holder: string; kind: "bank" | "card" | "fund"; active: boolean };

/** GET /credentials/{id}/verify: the connecting screen's state. */
export type VerifyStatus = {
  run_id: number;
  stage: "sending" | "connecting" | "otp" | "verifying" | "success" | "failed";
  otp_expires_at: string | null;
  failure_kind: string | null;
  error: string | null;
  accounts: AccountBrief[];
  credential: Credential;
  prefill: Record<string, string>; // a new connection's non-secret fields, to fix them
};

export type Account = {
  id: number;
  credential_id: number;
  provider: string;
  kind: "bank" | "card" | "fund";
  display_name: string;
  label: string;
  holder: string; // whose account: set by the user/provider, else the login owner
  excluded: boolean;
  balance: Money | null;
  balance_as_of: string | null;
  active: boolean; // cards: used in the last 6 months or carrying a balance
};

export type Transaction = {
  id: number;
  account_id: number;
  account_name: string;
  account_holder: string;
  cycle_shift: CycleShift | null;
  cycle_label: string | null;
  fixed_income_id: number | null;
  cycle_date_source: "auto" | "manual" | null;
  date: string;
  processed_date: string;
  amount: Money;
  original_amount: Money | null;
  original_currency: string | null;
  description: string;
  memo: string | null;
  installment_number: number | null;
  installment_total: number | null;
  status: "pending" | "completed";
  category_id: number | null;
  category_name: string | null;
  category_source: string | null;
  merchant_key: string | null;
  reconcile_status?: ReconcileStatus | null;
};

export type Page<T> = { items: T[]; next_cursor: string | null };

export type OtpRequest = { id: number; credential_label: string; provider: string; expires_at: string };

// Phases 2–6 (api-contract.md). Money here is number.
export type Group = "income" | "fixed" | "variable" | "savings" | "transfer" | "card_bill" | "ignore";
export type Category = { id: number; name: string; group: Group; sort_order: number };
export type Uncategorized = { merchant_key: string; sample_description: string; count: number; total: number; kind: "bank" | "card"; sample_date: string; account_label: string };
export type Cycle = { start: string; end: string; label_year: number; label_month: number };

export type CashFlow = {
  cycle: Cycle;
  income: number;
  spending: number;
  net: number;
  verdict: "positive" | "negative";
  groups: { group: "fixed" | "variable" | "savings" | "income"; total: number; categories: { category_id: number | null; name: string; total: number; count: number }[] }[];
  uncategorized_total: number;
  uncategorized_count: number;
  pending_count: number;
  income_fixed: number;
  income_variable: number;
  basis: string;
  history: (Cycle & { net: number })[];
  fees: Fees;
};

export type FeeItem = { txn_id: number; date: string; description: string; account_id: number; account_name: string; merchant_key: string; fee_key: string; amount: number };
export type Fees = { total: number; count: number; previous_total: number; items: FeeItem[]; new_fee_merchants: string[] };

export type Plan = {
  cycle: Cycle;
  today: string;
  expected_income: number;
  expected_fixed: number;
  goal: number; // goal_personal + goal_plans
  goal_personal: number;
  goal_plans: number;
  variable_allowance: number;
  variable_spent: number;
  variable_left: number;
  savings_spent: number;
  weeks: { start: string; end: string; spent: number; allowance: number; left: number; is_current: boolean; is_past: boolean }[];
  categories: { category_id: number | null; name: string; spent: number; expected: number; left: number }[];
  balances: { bank_total: number; accounts: { id: number; display_name: string; balance: number; as_of: string | null }[]; upcoming_card_charges: number };
  next_cycle: { installments_stopping_total: number; fixed_total: number; income_total: number };
  fees: { total: number; count: number };
  still_expected: ForecastItem[];
  still_expected_income: ForecastItem[];
};

export type ForecastItem = { label: string; amount: number; date: string; source: string; basis: string; charged: boolean; account_id: number | null; account_label: string | null; previous_account_label: string | null; category_name: string | null };
export type Forecast = {
  cycle: Cycle;
  fixed_total: number;
  income_total: number;
  installments_stopping_total: number;
  delta_fixed_vs_current: number;
  fixed_items: ForecastItem[];
  income_items: ForecastItem[];
  installments_stopping: ForecastItem[];
};

export type Recurring = {
  id: number;
  merchant_key: string;
  direction: "expense" | "income";
  label: string;
  category_id: number | null;
  category_name: string | null;
  cadence: string;
  amount_kind: "fixed" | "variable";
  expected_amount: number;
  last_date: string;
  next_expected_date: string;
  status: "pending" | "confirmed" | "dismissed";
  basis: string;
  account_id: number | null;
  account_label: string | null;
  previous_account_label: string | null;
  user_defined: boolean; // fixed income marked by the user
  expected_day: number | null;
};

export type Fund = {
  id: number;
  policy_id: string;
  name: string;
  product_type: string;
  owner: string;
  company: string | null;
  liquidity_date: string | null;
  latest_balance: number;
  as_of: string;
  ytd_profit: number;
  ytd_return_pct: number | null;
  fee_deposit_pct: number | null;
  fee_savings_pct: number | null;
  forecast_monthly_pension: number | null;
  monthly: { date: string; balance: number }[];
};
export type RetirementForecast = {
  credential_id: number;
  owner: string;
  report_month: string;
  forecast_monthly_pension: number | null;
  forecast_lump_sum: number | null;
  forecast_total_balance: number | null;
  total_savings: number | null;
};
export type Funds = { total: number; as_of: string | null; funds: Fund[]; credentials: { id: number; label: string; owner: string; last_success_at: string | null }[]; forecast: RetirementForecast[] };
export type FundDetail = {
  fund: Fund;
  yearly: { year: number; start_balance: number; deposits: number; profit: number; end_balance: number; return_pct: number | null }[];
  deposits: { date: string; amount: number }[];
};

export type Notification = { id: number; created_at: string; kind: string; severity: "info" | "warning" | "critical"; title: string; body: string; link: string | null; read_at: string | null };
export type Settings = { cycle_start_day: number; month_end_goal_default: number };

export type ReconcileStatus = "matched" | "mismatch" | "unknown_card";
export type BillReconciliation = {
  bank_txn_id: number;
  date: string;
  amount: number;
  issuer: string | null;
  status: ReconcileStatus;
  matched_accounts: { id: number; name: string; excluded: boolean }[];
  matched_account_ids: number[];
  card_total: number;
  gap: number;
  suggestions: { txn_id: number; description: string; amount: number; date: string; account_id: number; reason: string }[];
};
export type Reconcile = { cycle: Cycle; bills: BillReconciliation[]; matched_count: number; mismatch_count: number; unknown_count: number };

export type SavingsPlan = {
  id: number;
  name: string;
  target_amount: number;
  target_date: string;
  saved_amount: number;
  monthly_override: number | null;
  active: boolean;
  created_at: string;
  months_left: number;
  monthly_needed: number;
  funded_this_cycle: boolean;
  completed: boolean;
  overdue: boolean; // target date passed; no longer part of monthly_total
};
export type SavingsPlans = { monthly_total: number; active_count: number; plans: SavingsPlan[] };

export type Cost = {
  total: number;
  count: number;
  monthly: { label_year: number; label_month: number; total: number }[];
  top_merchants: { merchant_key: string; sample: string; total: number; count: number }[];
  avg_per_month: number;
};

export type WhatIfNumbers = { variable_allowance: number; weekly_left: number; month_end: number };
export type WhatIf = { baseline: WhatIfNumbers; scenario: WhatIfNumbers; monthly_delta: number; yearly_impact: number };

export type Insight = {
  key: string;
  kind: string;
  severity: "info" | "warning" | "positive";
  title: string;
  body: string;
  action_label: string | null;
  link: string | null;
  amount: number | null;
};

export type CategoryChange = { category_id: number | null; name: string; previous: number; current: number; change_pct: number };
export type Progress = {
  cycles: { cycle: Cycle; net: number }[];
  avg_net: number;
  positive_cycles: number;
  savings_total: number;
  savings_avg: number;
  increases: CategoryChange[];
  decreases: CategoryChange[];
  cumulative_net: number;
  since: string | null;
};
