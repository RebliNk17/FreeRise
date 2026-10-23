import { expect, test } from "bun:test";
import { holderChoices, parseHidden, withHidden } from "./viewFilter";

test("parseHidden tolerates junk", () => {
  expect(parseHidden("[1,2]")).toEqual([1, 2]);
  expect(parseHidden("nope")).toEqual([]);
  expect(parseHidden('{"a":1}')).toEqual([]);
  expect(parseHidden('[1,"x",2.5]')).toEqual([1]);
  expect(parseHidden(null)).toEqual([]);
});

test("withHidden adds the query param only when needed", () => {
  expect(withHidden("/home/current", [])).toBe("/home/current");
  expect(withHidden("/home/current", [3, 4])).toBe("/home/current?hide_accounts=3,4");
  expect(withHidden("/x?a=1", [3])).toBe("/x?a=1&hide_accounts=3");
});

test("holderChoices: one per holder, only with 2+ holders", () => {
  const accts = [
    { id: 1, holder: "שי" },
    { id: 2, holder: "נועה" },
    { id: 3, holder: "שי" },
  ];
  expect(holderChoices(accts)).toEqual([
    { holder: "שי", hide: [2] },
    { holder: "נועה", hide: [1, 3] },
  ]);
  expect(holderChoices(accts.filter((a) => a.holder === "שי"))).toEqual([]);
});
