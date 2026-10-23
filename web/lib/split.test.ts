import { expect, test } from "bun:test";
import { splitBody, splitLeft, splitProblem } from "./split";

test("splitLeft is cent-exact", () => {
  expect(splitLeft(-100.3, [{ category_id: 1, amount: "50.1" }, { category_id: 2, amount: "50.2" }])).toBe(0);
  expect(splitLeft(-100, [{ category_id: 1, amount: "40" }])).toBe(60);
});

test("splitProblem", () => {
  const ok = [
    { category_id: 1, amount: "60" },
    { category_id: 2, amount: "40" },
  ];
  expect(splitProblem(-100, ok)).toBeNull();
  expect(splitProblem(-100, ok.slice(0, 1))).not.toBeNull();
  expect(splitProblem(-100, [ok[0], { category_id: 1, amount: "40" }])).toBe("כל קטגוריה פעם אחת");
  expect(splitProblem(-100, [ok[0], { category_id: 2, amount: "30" }])).not.toBeNull();
  expect(splitProblem(-100, [ok[0], { category_id: null, amount: "40" }])).not.toBeNull();
});

test("splitBody applies the transaction's sign", () => {
  expect(splitBody(-100, [{ category_id: 1, amount: "60" }, { category_id: 2, amount: "40" }]).parts.map((p) => p.amount)).toEqual([-60, -40]);
  expect(splitBody(100, [{ category_id: 1, amount: "60" }, { category_id: 2, amount: "40" }]).parts.map((p) => p.amount)).toEqual([60, 40]);
});
