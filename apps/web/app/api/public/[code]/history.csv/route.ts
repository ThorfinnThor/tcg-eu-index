import { NextResponse } from "next/server";
import { getIndex } from "@/lib/data";

export const revalidate = 3600;

export async function GET(_request: Request, { params }: { params: { code: string } }) {
  const index = await getIndex(params.code);
  if (!index) return NextResponse.json({ error: "Unknown index" }, { status: 404 });
  const lines = ["value_date,index_value,daily_return,n_constituents_active"];
  lines.push(
    ...index.history.map((row) =>
      [row.value_date, row.index_value.toFixed(6), row.daily_return.toFixed(8), row.n_constituents_active].join(",")
    )
  );
  return new NextResponse(lines.join("\n") + "\n", {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Cache-Control": "public, max-age=3600"
    }
  });
}
