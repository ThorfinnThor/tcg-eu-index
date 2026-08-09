import { z } from "zod";
import type { Constituent, DailyIndexValue } from "./types";

export const holdingSchema = z.object({
  cm_product_id: z.coerce.number().int().positive(),
  variant_key: z.string().trim().default("nonfoil"),
  quantity: z.coerce.number().positive(),
  cost_basis_eur: z.coerce.number().optional()
});

export type Holding = z.infer<typeof holdingSchema>;
export type ParsedHoldingRow =
  | { line: number; ok: true; holding: Holding }
  | { line: number; ok: false; error: string };

export type AcceptedHolding = {
  line: number;
  holding: Holding;
  constituent: Constituent;
  market_value_eur: number;
  cost_basis_value_eur: number | null;
};

export type PortfolioValidation = {
  accepted: AcceptedHolding[];
  errors: Array<{ line: number; error: string }>;
};

export type PortfolioComparisonPoint = {
  value_date: string;
  portfolio: number;
  benchmark: number;
  relative_pp: number;
};

const requiredColumns = ["cm_product_id", "quantity"];

function parseCsvLine(line: string) {
  return line.split(",").map((item) => item.trim());
}

function constituentKey(productId: number, variantKey: string) {
  return `${productId}:${variantKey.trim() || "nonfoil"}`;
}

export function buildConstituentLookup(constituents: Constituent[]) {
  return new Map(constituents.map((item) => [constituentKey(item.cm_product_id, item.variant_key), item]));
}

export function parsePortfolioCsv(csv: string): ParsedHoldingRow[] {
  const lines = csv.trim().split(/\r?\n/).filter(Boolean);
  if (lines.length === 0) return [{ line: 1, ok: false, error: "CSV is empty" }];
  const [header, ...rows] = lines;
  const columns = parseCsvLine(header);
  const missing = requiredColumns.filter((column) => !columns.includes(column));
  if (missing.length > 0) {
    return [{ line: 1, ok: false, error: `Missing required column: ${missing.join(", ")}` }];
  }
  return rows.map((line, index) => {
    const values = parseCsvLine(line);
    const record = Object.fromEntries(columns.map((column, columnIndex) => [column, values[columnIndex]]));
    const parsed = holdingSchema.safeParse({
      ...record,
      variant_key: record.variant_key || "nonfoil",
      cost_basis_eur: record.cost_basis_eur || undefined
    });
    if (!parsed.success) {
      return { line: index + 2, ok: false as const, error: parsed.error.issues[0]?.message ?? "Invalid row" };
    }
    return { line: index + 2, ok: true as const, holding: parsed.data };
  });
}

export function validatePortfolioCsv(csv: string, constituents: Constituent[]): PortfolioValidation {
  const lookup = buildConstituentLookup(constituents);
  const accepted: AcceptedHolding[] = [];
  const errors: Array<{ line: number; error: string }> = [];

  for (const row of parsePortfolioCsv(csv)) {
    if (!row.ok) {
      errors.push({ line: row.line, error: row.error });
      continue;
    }

    const constituent = lookup.get(constituentKey(row.holding.cm_product_id, row.holding.variant_key));
    if (!constituent) {
      errors.push({
        line: row.line,
        error: `Unmatched Cardmarket product ${row.holding.cm_product_id} (${row.holding.variant_key})`
      });
      continue;
    }

    accepted.push({
      line: row.line,
      holding: row.holding,
      constituent,
      market_value_eur: Number((constituent.ref_price * row.holding.quantity).toFixed(2)),
      cost_basis_value_eur:
        typeof row.holding.cost_basis_eur === "number"
          ? Number((row.holding.cost_basis_eur * row.holding.quantity).toFixed(2))
          : null
    });
  }

  return { accepted, errors };
}

export function summarizePortfolio(validation: PortfolioValidation, history: DailyIndexValue[]) {
  const latestMarketValue = validation.accepted.reduce((sum, item) => sum + item.market_value_eur, 0);
  const providedCostBasis = validation.accepted.reduce((sum, item) => sum + (item.cost_basis_value_eur ?? 0), 0);
  const hasCostBasis = validation.accepted.some((item) => item.cost_basis_value_eur !== null);
  const first = history.at(0)?.index_value ?? 1000;
  const latest = history.at(-1)?.index_value ?? first;
  const benchmarkReturn = latest / first - 1;
  const portfolioReturn = hasCostBasis && providedCostBasis > 0 ? latestMarketValue / providedCostBasis - 1 : null;

  return {
    latestMarketValue: Number(latestMarketValue.toFixed(2)),
    providedCostBasis: hasCostBasis ? Number(providedCostBasis.toFixed(2)) : null,
    portfolioReturn,
    benchmarkReturn,
    relativePp: portfolioReturn === null ? null : Number(((portfolioReturn - benchmarkReturn) * 100).toFixed(2))
  };
}

export function buildPortfolioComparison(history: DailyIndexValue[], validation: PortfolioValidation): PortfolioComparisonPoint[] {
  const summary = summarizePortfolio(validation, history);
  const first = history.at(0)?.index_value ?? 1000;
  const targetReturn = summary.portfolioReturn ?? summary.benchmarkReturn;

  return history.map((row, position) => {
    const progress = history.length <= 1 ? 1 : position / (history.length - 1);
    const benchmark = (row.index_value / first) * 1000;
    const portfolio = 1000 * (1 + targetReturn * progress);
    return {
      value_date: row.value_date,
      portfolio: Number(portfolio.toFixed(2)),
      benchmark: Number(benchmark.toFixed(2)),
      relative_pp: Number(((portfolio / benchmark - 1) * 100).toFixed(2))
    };
  });
}
