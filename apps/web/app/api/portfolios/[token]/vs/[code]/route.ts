import { NextResponse } from "next/server";
import { getIndex } from "@/lib/data";
import { buildPortfolioComparison, validatePortfolioCsv } from "@/lib/portfolio";

export async function GET(_request: Request, { params }: { params: { token: string; code: string } }) {
  const index = await getIndex(params.code);
  if (!index) return NextResponse.json({ error: "Unknown benchmark" }, { status: 404 });
  const emptyValidation = validatePortfolioCsv("cm_product_id,variant_key,quantity,cost_basis_eur\n", []);
  const series = buildPortfolioComparison(index.history, emptyValidation);
  return NextResponse.json({
    token: params.token,
    code: params.code,
    series,
    mode: "stateless-benchmark-only",
    note: "The JSON-only MVP does not persist uploaded holdings server-side; the interactive portfolio page calculates the holding-specific preview in the browser."
  });
}
