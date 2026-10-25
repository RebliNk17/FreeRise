/** Friendly Hebrew text for a failed sync / connection check, from the scraper's error type. */

export type FailureKey = "password" | "locked" | "blocked" | "changed" | "timeout" | "otp" | "otp_timeout" | "general";
export type Friendly = { key: FailureKey; short: string; title: string; hint: string };

const TEXT: Record<FailureKey, Omit<Friendly, "key">> = {
  password: { short: "סיסמה שגויה", title: "שם המשתמש או הסיסמה שגויים", hint: "בדקו את הפרטים ונסו שוב." },
  locked: {
    short: "נדרשת פעולה בבנק",
    title: "נדרשת פעולה באתר הספק",
    hint: "החשבון נעול או שנדרש להחליף סיסמה. היכנסו לאתר הספק, הסדירו את זה ואז עדכנו כאן את הפרטים.",
  },
  blocked: {
    short: "חסום זמנית",
    title: "הספק חוסם כרגע חיבור אוטומטי",
    hint: "זה לא קשור לפרטים שלכם ובדרך כלל חולף. נסו שוב מאוחר יותר.",
  },
  changed: { short: "האתר השתנה", title: "אתר הספק השתנה", hint: "החיבור לא מצליח לקרוא את האתר כרגע. נסו שוב מאוחר יותר." },
  timeout: { short: "תם הזמן", title: "החיבור לקח יותר מדי זמן", hint: "ייתכן שאתר הספק איטי כרגע. נסו שוב בעוד כמה דקות." },
  otp: { short: "קוד שגוי", title: "קוד האימות שגוי", hint: "אפשר לבקש קוד חדש ולנסות שוב." },
  otp_timeout: { short: "לא הוזן קוד", title: "לא הוזן קוד אימות בזמן", hint: "נסו שוב והזינו את הקוד כשהוא מגיע ב-SMS." },
  general: { short: "שגיאה", title: "החיבור נכשל", hint: "נסו שוב מאוחר יותר." },
};

// Scraper error types (upper: ErrorType; lower: LoginResult) in the stored "<TYPE>: <message>" text.
// Both engines store the same types (src/freerise/sync/ibs.py maps the npm package's onto them);
// GENERIC / GENERAL_ERROR / UNKNOWN_ERROR fall through to the run's failure_kind.
const BY_TEXT: [RegExp, FailureKey][] = [
  [/INVALID_OTP/i, "otp"],
  [/OTP not entered|TWO_FACTOR_RETRIEVER_MISSING/i, "otp_timeout"],
  [/INVALID_PASSWORD/i, "password"],
  [/CHANGE_PASSWORD|ACCOUNT_BLOCKED/i, "locked"],
  [/AUTOMATION_BLOCKED/, "blocked"],
  [/TIMEOUT/i, "timeout"],
];
const BY_KIND: Record<string, FailureKey> = {
  auth_failed: "password",
  timeout: "timeout",
  otp_timeout: "otp_timeout",
  provider_changed: "changed",
};

// A rejected login often says which fields were wrong; name those instead of "username or password".
const WRONG_FIELDS: [RegExp, string, string][] = [
  [/ID or card6Digits/i, "תעודת הזהות או 6 הספרות של הכרטיס שגויים", "בדקו את מספר תעודת הזהות ואת 6 הספרות הראשונות של הכרטיס, ונסו שוב."],
  [/phone number or password/i, "מספר הטלפון או הסיסמה שגויים", "בדקו את מספר הטלפון ואת הסיסמה, ונסו שוב."],
  [/invalid password|rejected the password/i, "הסיסמה שגויה", "בדקו את הסיסמה ונסו שוב."],
];

export function friendlyError(kind: string | null | undefined, error: string | null | undefined): Friendly {
  const key = BY_TEXT.find(([re]) => re.test(error ?? ""))?.[1] ?? BY_KIND[kind ?? ""] ?? "general";
  const fields = key === "password" ? WRONG_FIELDS.find(([re]) => re.test(error ?? "")) : undefined;
  return { key, ...TEXT[key], ...(fields && { title: fields[1], hint: fields[2] }) };
}

/** Raw text for the collapsed "פרטים טכניים", minus remediation advice (proxies, show_browser…). */
export function technicalDetails(error: string | null | undefined): string {
  const t = (error ?? "").replace(/\s*\b(Consider|Suggestions?|Recommendations?)\b\s*:[\s\S]*$/i, "");
  return t
    .split(/(?<=[.;!])\s+/)
    .filter((s) => !/prox|show_browser|headless|stealth|captcha|user.?agent/i.test(s))
    .join(" ")
    .trim();
}
