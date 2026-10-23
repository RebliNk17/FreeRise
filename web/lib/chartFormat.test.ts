import { expect, test } from "bun:test";
import { captionIndex, compactMoney } from "./chartFormat";

test("compactMoney", () => {
  expect(compactMoney(8645.9)).toBe("8.6K");
  expect(compactMoney(950)).toBe("950");
  expect(compactMoney(-1200)).toBe("-1.2K");
  expect(compactMoney(12000)).toBe("12K");
  expect(compactMoney(150000)).toBe("150K");
  expect(compactMoney(1250000)).toBe("1.3M");
  expect(compactMoney(0)).toBe("0");
});

test("captionIndex", () => {
  expect(captionIndex(6, null)).toBe(5);
  expect(captionIndex(6, 2)).toBe(2);
  expect(captionIndex(6, 9)).toBe(5);
  expect(captionIndex(0, null)).toBe(-1);
});
