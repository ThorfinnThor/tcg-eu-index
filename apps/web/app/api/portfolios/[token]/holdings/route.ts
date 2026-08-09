import { NextResponse } from "next/server";
import { parsePortfolioCsv } from "@/lib/portfolio";

export async function PUT(request: Request, { params }: { params: { token: string } }) {
  const csv = await request.text();
  const parsed = parsePortfolioCsv(csv);
  const errors = parsed.filter((row) => !row.ok);
  const holdings = parsed.filter((row) => row.ok);
  return NextResponse.json({
    token: params.token,
    accepted: holdings.length,
    errors
  });
}
