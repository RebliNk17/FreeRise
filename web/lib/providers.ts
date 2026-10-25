const PROVIDER_NAMES: Record<string, string> = {
  hapoalim: "בנק הפועלים",
  leumi: "בנק לאומי",
  discount: "בנק דיסקונט",
  mercantile: "בנק מרכנתיל",
  mizrahi: "מזרחי טפחות",
  "otsar hahayal": "בנק אוצר החייל",
  union: "בנק איגוד",
  beinleumi: "הבינלאומי",
  massad: "בנק מסד",
  yahav: "בנק יהב",
  onezero: "וואן זירו",
  pagi: "בנק פאג״י",
  pepper: "פפר",
  max: "מקס",
  "visa cal": "כאל",
  isracard: "ישראכרט",
  amex: "אמריקן אקספרס",
  "beyahad bishvilha": "ביחד בשבילך",
  behatsdaa: "בהצדעה",
  hafenix: "הפניקס",
  migdal: "מגדל",
  mislaka: "המסלקה הפנסיונית",
  demo: "בנק הדגמה", // fake provider, demo mode only
};

// Files in public/providers/ (see README there). Missing → ProviderLogo draws a monogram.
const LOGO_FILES = new Set([
  "hapoalim.svg", "leumi.svg", "discount.svg", "mercantile.svg", "mizrahi.svg", "otsar-hahayal.svg", "union.svg",
  "beinleumi.svg", "massad.svg", "yahav.svg", "onezero.svg", "pepper.svg", "max.svg", "visa-cal.svg", "isracard.svg", "amex.svg",
  "beyahad-bishvilha.png", "behatsdaa.svg", "mislaka.svg",
]);

// English names people search by that the key doesn't already contain ("cal" is in "visa cal").
const ALIASES: Record<string, string> = {
  hafenix: "phoenix haphoenix",
  mizrahi: "tefahot",
  "otsar hahayal": "otzar",
  beinleumi: "international fibi",
  amex: "american express",
  union: "igud",
  "visa cal": "kal",
  mislaka: "clearing house",
};

/** Search text for the provider picker, next to the Hebrew name: the key plus English aliases. */
export const providerKeywords = (key: string) => `${key} ${ALIASES[key] ?? ""}`.trim();

export const SERVICE_LABELS: Record<string, string> = {
  banks: "בנקים",
  credit_cards: "כרטיסי אשראי",
  insurances: "פנסיה וחיסכון",
};

/** "/providers/visa-cal.svg", or null when there is no logo file for `key`. */
export function providerLogo(key: string): string | null {
  const base = key.replaceAll(" ", "-");
  const file = [`${base}.svg`, `${base}.png`].find((f) => LOGO_FILES.has(f));
  return file ? `/providers/${file}` : null;
}

const FIELD_LABELS: Record<string, string> = {
  id: "תעודת זהות",
  password: "סיסמה",
  username: "שם משתמש",
  card6Digits: "6 ספרות הכרטיס",
  card8Digits: "8 ספרות הכרטיס",
  card4Digits: "4 ספרות אחרונות של הכרטיס",
  bankAccountNum: "מספר חשבון הבנק",
  email: "אימייל",
  phoneNumber: "טלפון",
  userCode: "קוד משתמש",
  num: "קוד מזהה",
  nationalID: "תעודת זהות",
  otpLongTermToken: "אסימון התחברות",
};

export const providerName = (key: string) => PROVIDER_NAMES[key] ?? key;
export const fieldLabel = (key: string) => FIELD_LABELS[key] ?? key;
export const isSecretField = (key: string) => key.includes("password") || key.includes("Token");

/** Login method switch label; a method without a password logs in with an SMS code. */
export const methodLabel = (fields: string[]) =>
  fields.some(isSecretField) ? "סיסמה" : fields.includes("bankAccountNum") ? "חשבון בנק + SMS" : "כרטיס + SMS";

/** Index of the method a saved login uses: the first whose fields are all stored (else 0). */
export const storedMethod = (methods: string[][], stored: string[]) =>
  Math.max(0, methods.findIndex((m) => m.every((f) => stored.includes(f))));

/** Non-empty, trimmed form values for `keys` (inputs named `field:<key>`). Empty = keep/omit. */
export function filledFields(keys: string[], form: { get(name: string): unknown }): Record<string, string> {
  const out: Record<string, string> = {};
  for (const k of keys) {
    const v = String(form.get(`field:${k}`) ?? "").trim();
    if (v) out[k] = v;
  }
  return out;
}
