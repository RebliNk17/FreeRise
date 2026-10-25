// Insight card helpers: amount bolding, kind → illustration, severity → band theme.
import type { Insight } from "./api";

/** "יחסרו ₪1,200." → [{text:"יחסרו ", bold:false}, {text:"₪1,200", bold:true}, {text:".", bold:false}]. */
const AMOUNT = /(₪\s?[\d,.]*\d|\d[\d,.]*\s?₪)/; // ponytail: no minus — Hebrew "ו-₪12" uses "-" as a prefix joiner
export function splitAmounts(body: string): { text: string; bold: boolean }[] {
  return body
    .split(AMOUNT)
    .map((text, k) => ({ text, bold: k % 2 === 1 }))
    .filter((p) => p.text);
}

export type IllustrationName = "spike" | "drain" | "piggy" | "receipt" | "card" | "sunrise" | "shrink" | "coin";

export function illustrationFor(kind: string, severity: Insight["severity"]): IllustrationName {
  switch (kind) {
    case "category_up":
    case "category_creep":
      return "spike";
    case "category_down":
    case "installments_stopping":
      return "shrink";
    case "category_trend":
      return severity === "positive" ? "shrink" : "spike";
    case "negative_cycle":
    case "low_balance_before_income":
      return "drain";
    case "idle_cash":
    case "saving_capacity":
      return "piggy";
    case "fees":
    case "fixed_not_charged":
      return "receipt";
    case "unknown_card":
      return "card";
    case "no_goal":
    case "goal_status":
    case "goal_on_track":
    case "goal_at_risk":
      return "sunrise";
    default:
      return "coin";
  }
}

/** Read before the title by screen readers: the band colour alone carries the severity. */
export const SEVERITY_WORD: Record<Insight["severity"], string> = { warning: "אזהרה", positive: "חיובי", info: "מידע" };

/** Literal class names so Tailwind picks them up; colors live in globals.css (--band-*). */
export const BAND: Record<Insight["severity"], string> = {
  warning: "bg-band-warning",
  positive: "bg-band-positive",
  info: "bg-band-info",
};

const CTA: Record<IllustrationName, string> = {
  spike: "לפירוט הקטגוריה",
  shrink: "לפירוט הקטגוריה",
  drain: "לתחזית",
  piggy: "לחיסכון",
  receipt: "לפירוט העמלות",
  card: "לפירוט החיובים",
  sunrise: "ליעד החודשי",
  coin: "לפרטים",
};

/** Button label, or null when there's nowhere to go. */
export const ctaLabel = (it: Pick<Insight, "kind" | "severity" | "action_label" | "link">) =>
  it.link ? (it.action_label ?? CTA[illustrationFor(it.kind, it.severity)]) : null;

/** Longest card intro (globals.css a-* classes); auto-advance waits for it. */
export const INTRO_MS = 1400;
export const ADVANCE_MS = 12_000;

/** ms until the next auto-advance, or null when it shouldn't run. Any user interaction stops it for the visit. */
export function advanceDelay(s: { n: number; reduced: boolean; hover: boolean; focus: boolean; hidden: boolean; interacted: boolean; dragging: boolean }) {
  if (s.n < 2 || s.reduced || s.hover || s.focus || s.hidden || s.interacted || s.dragging) return null;
  return INTRO_MS + ADVANCE_MS;
}
