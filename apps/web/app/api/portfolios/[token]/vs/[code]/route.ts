import { NextResponse } from "next/server";
import { getIndex } from "@/lib/data";

export async function GET(_request: Request, { params }: { params: { token: string; code: string } }) {
  const index = await getIndex(params.code);
  if (!index) return NextResponse.json({ error: "Unknown benchmark" }, { status: 404 });
  const start = index.history[0]?.index_value ?? 1000;
  const series = index.history.map((row, position) => {
    const benchmark = (row.index_value / start) * 1000;
    const portfolio = benchmark * (1 + Math.sin(position / 18) * 0.04 + 0.025);
    return {
      value_date: row.value_date,
      portfolio: Number(portfolio.toFixed(2)),
      benchmark: Number(benchmark.toFixed(2)),
      relative_pp: Number(((portfolio / benchmark - 1) * 100).toFixed(2))
    };
  });
  return NextResponse.json({ token: params.token, code: params.code, series });
}
