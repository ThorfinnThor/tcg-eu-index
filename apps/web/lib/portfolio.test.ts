import { describe, expect, it } from "vitest";
import { buildPortfolioComparison, parsePortfolioCsv, summarizePortfolio, validatePortfolioCsv } from "./portfolio";
import type { Constituent, DailyIndexValue } from "./types";

const constituents: Constituent[] = [
  {
    cm_product_id: 750001,
    variant_key: "nonfoil",
    name: "Benchmark Product",
    set: "Launch Set",
    member_since: "2026-07-20",
    action: "retained",
    liquidity_score: 0.9,
    ref_price: 10
  }
];

const history: DailyIndexValue[] = [
  { value_date: "2026-07-20", index_value: 1000, daily_return: 0, n_constituents_active: 1 },
  { value_date: "2026-07-21", index_value: 1100, daily_return: 0.1, n_constituents_active: 1 }
];

describe("parsePortfolioCsv", () => {
  it("parses valid holdings and defaults variant", () => {
    const rows = parsePortfolioCsv("cm_product_id,variant_key,quantity,cost_basis_eur\n750123,,3,12.50\n");
    expect(rows[0]).toMatchObject({ ok: true, holding: { variant_key: "nonfoil", quantity: 3 } });
  });

  it("reports invalid rows", () => {
    const rows = parsePortfolioCsv("cm_product_id,variant_key,quantity\nbad,nonfoil,0\n");
    expect(rows[0]).toMatchObject({ ok: false, line: 2 });
  });

  it("requires the product and quantity headers", () => {
    const rows = parsePortfolioCsv("variant_key,cost_basis_eur\nnonfoil,3\n");
    expect(rows[0]).toMatchObject({ ok: false, line: 1 });
  });
});

describe("validatePortfolioCsv", () => {
  it("matches holdings against known constituents", () => {
    const result = validatePortfolioCsv("cm_product_id,variant_key,quantity,cost_basis_eur\n750001,nonfoil,2,8\n", constituents);
    expect(result.errors).toEqual([]);
    expect(result.accepted[0]).toMatchObject({ market_value_eur: 20, cost_basis_value_eur: 16 });
  });

  it("reports unmatched IDs without dropping the error", () => {
    const result = validatePortfolioCsv("cm_product_id,variant_key,quantity\n999999,nonfoil,1\n", constituents);
    expect(result.accepted).toHaveLength(0);
    expect(result.errors[0]).toMatchObject({ line: 2 });
    expect(result.errors[0]?.error).toContain("Unmatched");
  });
});

describe("portfolio comparison", () => {
  it("summarizes relative performance when cost basis is provided", () => {
    const validation = validatePortfolioCsv("cm_product_id,variant_key,quantity,cost_basis_eur\n750001,nonfoil,2,8\n", constituents);
    const summary = summarizePortfolio(validation, history);
    expect(summary.latestMarketValue).toBe(20);
    expect(summary.portfolioReturn).toBeCloseTo(0.25);
    expect(summary.benchmarkReturn).toBeCloseTo(0.1);
    expect(summary.relativePp).toBeCloseTo(15);
  });

  it("builds an aligned portfolio and benchmark series", () => {
    const validation = validatePortfolioCsv("cm_product_id,variant_key,quantity,cost_basis_eur\n750001,nonfoil,2,8\n", constituents);
    const series = buildPortfolioComparison(history, validation);
    expect(series).toHaveLength(2);
    expect(series[0]).toMatchObject({ value_date: "2026-07-20", portfolio: 1000, benchmark: 1000 });
    expect(series[1]).toMatchObject({ value_date: "2026-07-21", portfolio: 1250, benchmark: 1100 });
  });
});
