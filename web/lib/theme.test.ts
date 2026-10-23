import { expect, test } from "bun:test";
import { getTheme } from "./theme";

test("getTheme defaults to system and never throws", () => {
  expect(getTheme()).toBe("system"); // no localStorage in bun -> caught
  const store: Record<string, string> = { "freerise-theme": "dark" };
  (globalThis as unknown as Record<string, unknown>).localStorage = { getItem: (k: string) => store[k] ?? null };
  expect(getTheme()).toBe("dark");
  store["freerise-theme"] = "junk";
  expect(getTheme()).toBe("system");
  delete (globalThis as unknown as Record<string, unknown>).localStorage;
});
