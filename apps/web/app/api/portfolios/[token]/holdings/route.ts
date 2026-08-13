import { NextResponse } from "next/server";
import { codes, getConstituents, getIndexes } from "@/lib/data";
import { validatePortfolioCsv } from "@/lib/portfolio";
import { isRateLimited, requestIp, validPortfolioToken } from "@/lib/request-guards";

export async function PUT(request: Request, { params }: { params: { token: string } }) {
  if (!validPortfolioToken(params.token)) {
    return NextResponse.json({ error: "Invalid portfolio token" }, { status: 400 });
  }
  if (isRateLimited(`portfolio-holdings:${requestIp(request)}`)) {
    return NextResponse.json({ error: "Too many requests" }, { status: 429 });
  }
  if (Number(request.headers.get("content-length") ?? 0) > 1_000_000) {
    return NextResponse.json({ error: "CSV exceeds the 1 MB limit" }, { status: 413 });
  }
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
