import { describe, expect, it } from "vitest";
import { chartPoints, historyForRange } from "./index-analytics";
import type { DailyIndexValue } from "./types";

const history: DailyIndexValue[] = [
  { value_date: "2025-07-01", index_value: 1000, daily_return: 0, n_constituents_active: 10 },
  { value_date: "2026-06-15", index_value: 1200, daily_return: 0.2, n_constituents_active: 10 },
  { value_date: "2026-07-15", index_value: 900, daily_return: -0.25, n_constituents_active: 10 }
];

describe("historyForRange", () => {
  it("filters relative to the latest observation", () => {
    expect(historyForRange(history, "1M").map((row) => row.value_date)).toEqual(["2026-06-15", "2026-07-15"]);
  });

  it("keeps the complete series for Max", () => {
    expect(historyForRange(history, "Max")).toBe(history);
  });
});

describe("chartPoints", () => {
  it("calculates drawdown against the running peak", () => {
    expect(chartPoints(history).map((point) => point.drawdown)).toEqual([0, 0, -25]);
  });
});
