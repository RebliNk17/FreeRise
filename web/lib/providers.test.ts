import { expect, test } from "bun:test";
import { filterOptions } from "./listbox";
import { fieldLabel, filledFields, isSecretField, methodLabel, providerKeywords, providerLogo, providerName, storedMethod } from "./providers";

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

const MAX = [["username", "password"], ["id", "card8Digits"], ["id", "bankAccountNum"]];
const ISRACARD = [["id", "card6Digits", "password"], ["id", "card6Digits"]];

test("method labels", () => {
  expect(MAX.map(methodLabel)).toEqual(["סיסמה", "כרטיס + SMS", "חשבון בנק + SMS"]);
  expect(ISRACARD.map(methodLabel)).toEqual(["סיסמה", "כרטיס + SMS"]);
});

test("the stored login picks its method", () => {
  expect(storedMethod(MAX, ["username", "password", "id", "otpLongTermToken"])).toBe(0);
  expect(storedMethod(MAX, ["id", "card8Digits", "otpLongTermToken"])).toBe(1);
  expect(storedMethod(MAX, ["id", "bankAccountNum"])).toBe(2);
  // the password method holds the SMS one's fields too: a stored password wins, as in the engine
  expect(storedMethod(ISRACARD, ["id", "card6Digits", "password"])).toBe(0);
  expect(storedMethod(ISRACARD, ["id", "card6Digits"])).toBe(1);
  expect(storedMethod(MAX, [])).toBe(0);
});

test("provider search finds English names too", () => {
  const keys = ["hapoalim", "leumi", "onezero", "pepper", "max", "visa cal", "isracard", "amex", "hafenix", "migdal"];
  const options = keys.map((k) => ({ value: k, label: providerName(k), keywords: providerKeywords(k) }));
  const find = (q: string) => filterOptions(options, q).map((o) => o.value);
  expect(find("cal")).toEqual(["visa cal"]);
  expect(find("Phoenix")).toEqual(["hafenix"]);
  expect(find("poalim")).toEqual(["hapoalim"]);
  expect(find("one zero")).toEqual(["onezero"]);
  expect(find("American Express")).toEqual(["amex"]);
  for (const k of ["max", "isracard", "pepper", "migdal", "leumi"]) expect(find(k.toUpperCase())).toEqual([k]);
  expect(find("כאל")).toEqual(["visa cal"]); // Hebrew still works
});
