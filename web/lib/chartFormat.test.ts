import { expect, test } from "bun:test";
import { captionIndex, chartMoney } from "./chartFormat";

test("chartMoney: exact, never rounded", () => {
  expect(chartMoney(8645.9)).toBe("8,645.9");
  expect(chartMoney(950)).toBe("950");
  expect(chartMoney(-1200)).toBe("-1,200");
  expect(chartMoney(1250000.55)).toBe("1,250,000.55");
  expect(chartMoney(0)).toBe("0");
});

test("captionIndex", () => {
  expect(captionIndex(6, null)).toBe(5);
  expect(captionIndex(6, 2)).toBe(2);
  expect(captionIndex(6, 9)).toBe(5);
  expect(captionIndex(0, null)).toBe(-1);
});
