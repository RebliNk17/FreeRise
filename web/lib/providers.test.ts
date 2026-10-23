import { expect, test } from "bun:test";
import { fieldLabel, filledFields, isSecretField, providerLogo, providerName } from "./providers";

test("secret fields", () => {
  expect(isSecretField("password")).toBe(true);
  expect(isSecretField("otpLongTermToken")).toBe(true);
  expect(isSecretField("id")).toBe(false);
});

test("labels fall back to key", () => {
  expect(fieldLabel("card6Digits")).toBe("6 ספרות הכרטיס");
  expect(fieldLabel("weird")).toBe("weird");
  expect(providerName("visa cal")).toBe("כאל");
  expect(providerName("x")).toBe("x");
});

test("filledFields drops empty values so the server keeps them", () => {
  const form = new Map<string, string>([
    ["field:password", " new-pw "],
    ["field:username", ""],
  ]);
  expect(filledFields(["password", "username", "id"], form)).toEqual({ password: "new-pw" });
});

test("provider logos map keys to files, null when missing", () => {
  expect(providerLogo("visa cal")).toBe("/providers/visa-cal.svg");
  expect(providerLogo("otsar hahayal")).toBe("/providers/otsar-hahayal.svg");
  expect(providerLogo("beyahad bishvilha")).toBe("/providers/beyahad-bishvilha.png");
  expect(providerLogo("hapoalim")).toBe("/providers/hapoalim.svg");
  expect(providerLogo("pagi")).toBeNull();
  expect(providerLogo("unknown")).toBeNull();
  expect(providerName("pagi")).toBe("בנק פאג״י");
  expect(fieldLabel("nationalID")).toBe("תעודת זהות");
});

test("every logo file named in the map exists", async () => {
  const keys = ["hapoalim", "leumi", "discount", "mercantile", "mizrahi", "otsar hahayal", "union", "beinleumi", "massad", "yahav", "onezero", "max", "visa cal", "isracard", "amex", "beyahad bishvilha", "behatsdaa", "mislaka"];
  for (const k of keys) {
    const src = providerLogo(k);
    expect(src).not.toBeNull();
    expect(await Bun.file(`${import.meta.dir}/../public${src}`).exists()).toBe(true);
  }
});
