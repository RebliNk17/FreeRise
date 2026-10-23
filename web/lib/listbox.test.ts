import { expect, test } from "bun:test";
import { filterOptions, moveIndex, typeahead, type Option } from "./listbox";

const opts: Option[] = [
  { value: "a", label: "Apple" },
  { value: "b", label: "Banana", disabled: true },
  { value: "c", label: "Cherry" },
  { value: "d", label: "avocado" },
];

test("moveIndex skips disabled and wraps", () => {
  expect(moveIndex(opts, 0, "ArrowDown")).toBe(2);
  expect(moveIndex(opts, 3, "ArrowDown")).toBe(0);
  expect(moveIndex(opts, 2, "ArrowUp")).toBe(0);
  expect(moveIndex(opts, 0, "ArrowUp")).toBe(3);
  expect(moveIndex(opts, -1, "ArrowDown")).toBe(0);
  expect(moveIndex(opts, 2, "Home")).toBe(0);
  expect(moveIndex(opts, 0, "End")).toBe(3);
  expect(moveIndex(opts, 2, "x")).toBe(2);
  expect(moveIndex([{ value: "z", label: "z", disabled: true }], 0, "ArrowDown")).toBe(-1);
});

test("typeahead: prefix match, case-insensitive, cycles on repeated letter", () => {
  expect(typeahead(opts, "a", -1)).toBe(0);
  expect(typeahead(opts, "a", 0)).toBe(3);
  expect(typeahead(opts, "aa", 3)).toBe(0);
  expect(typeahead(opts, "av", 0)).toBe(3);
  expect(typeahead(opts, "b", 0)).toBe(-1); // disabled
  expect(typeahead(opts, "ch", -1)).toBe(2);
  expect(typeahead(opts, "", 0)).toBe(-1);
  expect(typeahead([{ value: "h", label: "הפועלים" }], "ה", -1)).toBe(0);
});

test("filterOptions matches all terms anywhere", () => {
  expect(filterOptions(opts, "").length).toBe(4);
  expect(filterOptions(opts, "AN").map((o) => o.value)).toEqual(["b"]);
  expect(filterOptions(opts, "a o").map((o) => o.value)).toEqual(["d"]);
  expect(filterOptions(opts, "zzz")).toEqual([]);
});
