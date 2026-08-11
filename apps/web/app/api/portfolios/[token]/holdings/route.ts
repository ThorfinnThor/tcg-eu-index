import { NextResponse } from "next/server";
import { codes, getConstituents, getIndexes } from "@/lib/data";
import { validatePortfolioCsv } from "@/lib/portfolio";

export async function PUT(request: Request, { params }: { params: { token: string } }) {
  const indexes = await getIndexes();
  if (!indexes.some((index) => index.status === "published" && index.history.length > 0)) {
    return NextResponse.json({ error: "Portfolio matching requires published index data" }, { status: 409 });
  }
  const csv = await request.text();
  const constituents = (await Promise.all(codes().map((code) => getConstituents(code)))).flat();
  const validation = validatePortfolioCsv(csv, constituents);
  return NextResponse.json({
    token: params.token,
    accepted: validation.accepted.length,
    errors: validation.errors,
    holdings: validation.accepted.map((item) => ({
      line: item.line,
      cm_product_id: item.holding.cm_product_id,
      variant_key: item.holding.variant_key,
      quantity: item.holding.quantity,
      name: item.constituent.name,
      market_value_eur: item.market_value_eur
    })),
    mode: "json-only-mvp"
  });
}
