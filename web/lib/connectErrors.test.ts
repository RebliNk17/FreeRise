import { expect, test } from "bun:test";
import { friendlyError, technicalDetails } from "./connectErrors";

const BLOCKED =
  "AUTOMATION_BLOCKED: login failed: WAF challenge. Consider: 1) Using show_browser=True 2) Waiting 3) Using residential proxies";

test("error types map to friendly Hebrew", () => {
  expect(friendlyError("auth_failed", "INVALID_PASSWORD: login invalid_password: x").title).toBe("שם המשתמש או הסיסמה שגויים");
  expect(friendlyError("auth_failed", "INVALID_OTP: bad code").key).toBe("otp");
  expect(friendlyError("auth_failed", "ACCOUNT_BLOCKED: login account_blocked").key).toBe("locked");
  expect(friendlyError("auth_failed", "CHANGE_PASSWORD: x").key).toBe("locked");
  // blocked is not "site changed", although the backend buckets both as provider_changed
  expect(friendlyError("provider_changed", BLOCKED).key).toBe("blocked");
  expect(friendlyError("provider_changed", "GENERAL_ERROR: unexpected selector").key).toBe("changed");
  expect(friendlyError("timeout", "VERIFY_TIMEOUT: no progress").key).toBe("timeout");
  expect(friendlyError("otp_timeout", "OTP not entered in time").key).toBe("otp_timeout");
  expect(friendlyError(null, "something odd").key).toBe("general");
  expect(friendlyError(undefined, null).title).toBe("החיבור נכשל");
  // auto-disabled note prefix still classifies
  expect(friendlyError("auth_failed", "הושבת אוטומטית — יש לעדכן סיסמה: INVALID_PASSWORD: x").key).toBe("password");
});

test("israeli-bank-scrapers error types", () => {
  expect(friendlyError("auth_failed", "INVALID_PASSWORD: Login failed with INVALID_PASSWORD error").key).toBe("password");
  expect(friendlyError("auth_failed", "CHANGE_PASSWORD: no detail reported by the leumi scraper").key).toBe("locked");
  expect(friendlyError("auth_failed", 'ACCOUNT_BLOCKED: unexpected login result "ACCOUNT_BLOCKED"').key).toBe("locked");
  expect(friendlyError("timeout", "TIMEOUT: Navigation timeout of 30000 ms exceeded").key).toBe("timeout");
  expect(friendlyError("other", "TWO_FACTOR_RETRIEVER_MISSING: otpCodeRetriever is required").key).toBe("otp_timeout");
  expect(friendlyError("auth_failed", "INVALID_OTP: OneZero rejected the verification code").key).toBe("otp");
  expect(friendlyError("other", "GENERAL_ERROR: Cannot read properties of undefined").key).toBe("general");
  expect(friendlyError("provider_changed", "GENERAL_ERROR: unexpected response").key).toBe("changed");
});

test("a rejected login names the fields that were wrong", () => {
  expect(friendlyError("auth_failed", "INVALID_PASSWORD: Invalid ID or card6Digits").title).toBe("תעודת הזהות או 6 הספרות של הכרטיס שגויים");
  expect(friendlyError("auth_failed", "INVALID_PASSWORD: Pepper rejected the phone number or password").title).toBe("מספר הטלפון או הסיסמה שגויים");
  expect(friendlyError("auth_failed", "INVALID_PASSWORD: Invalid password").title).toBe("הסיסמה שגויה");
  expect(friendlyError("auth_failed", "INVALID_PASSWORD: no detail reported by the amex scraper").title).toBe("שם המשתמש או הסיסמה שגויים");
  expect(friendlyError("other", "GENERAL_ERROR: Invalid password").key).toBe("general"); // only refines a password failure
});

test("never suggests bypassing bot protection", () => {
  for (const k of ["auth_failed", "provider_changed", "timeout", "otp_timeout", "other"]) {
    const f = friendlyError(k, BLOCKED);
    expect(`${f.title} ${f.hint}`).not.toMatch(/proxy|פרוקסי|show_browser|VPN/i);
  }
});

test("technical details drop remediation advice", () => {
  const t = technicalDetails(BLOCKED);
  expect(t).toBe("AUTOMATION_BLOCKED: login failed: WAF challenge.");
  expect(technicalDetails("TIMEOUT: page load. Try a residential proxy. Then wait.")).toBe("TIMEOUT: page load. Then wait.");
  expect(technicalDetails(null)).toBe("");
});
