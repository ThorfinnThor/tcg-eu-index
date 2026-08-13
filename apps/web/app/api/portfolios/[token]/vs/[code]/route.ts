import { NextResponse } from "next/server";
import { getIndex } from "@/lib/data";
import { buildBenchmarkSeries } from "@/lib/portfolio";
import { isRateLimited, requestIp, validPortfolioToken } from "@/lib/request-guards";

export async function GET(_request: Request, { params }: { params: { token: string; code: string } }) {
  if (!validPortfolioToken(params.token)) {
    return NextResponse.json({ error: "Invalid portfolio token" }, { status: 400 });
  }
  if (isRateLimited(`portfolio-compare:${requestIp(_request)}`)) {
    return NextResponse.json({ error: "Too many requests" }, { status: 429 });
  }
  const index = await getIndex(params.code);
  if (!index) return NextResponse.json({ error: "Unknown benchmark" }, { status: 404 });
  if (index.status !== "published" || index.history.length === 0) {
    return NextResponse.json({ error: "Benchmark has not been published" }, { status: 409 });
  }
  const series = buildBenchmarkSeries(index.history);
  return NextResponse.json({
    token: params.token,
    code: params.code,
    series,
    mode: "stateless-benchmark-only",
    note: "The JSON-only MVP does not persist uploaded holdings server-side; the interactive portfolio page calculates the holding-specific preview in the browser."
  });
}
