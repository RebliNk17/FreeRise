import { expect, test } from "bun:test";
import { moveItem } from "./reorder";

test("moveItem", () => {
  expect(moveItem([1, 2, 3], 0, 1)).toEqual([2, 1, 3]);
  expect(moveItem([1, 2, 3], 2, -1)).toEqual([1, 3, 2]);
  expect(moveItem([1, 2, 3], 0, -1)).toEqual([1, 2, 3]);
  expect(moveItem([1, 2, 3], 2, 5)).toEqual([1, 2, 3]);
  expect(moveItem([1, 2, 3], 2, -2)).toEqual([3, 1, 2]);
});
