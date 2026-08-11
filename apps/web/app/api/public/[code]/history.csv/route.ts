import { NextResponse } from "next/server";
import { getIndex } from "@/lib/data";

export const revalidate = 3600;

export async function GET(_request: Request, { params }: { params: { code: string } }) {
  const index = await getIndex(params.code);
  if (!index) return NextResponse.json({ error: "Unknown index" }, { status: 404 });
  if (index.status !== "published" || index.history.length === 0) {
    return NextResponse.json(
      { error: "Index history has not been published", status: index.status },
      { status: 409, headers: { "Cache-Control": "public, max-age=3600" } }
    );
  }
  const lines = ["value_date,index_value,daily_return,n_constituents_active,n_capped,n_carried_forward,calc_version"];
  lines.push(
    ...index.history.map((row) =>
      [
        row.value_date,
        row.index_value.toFixed(6),
        row.daily_return.toFixed(8),
        row.n_constituents_active,
        row.n_capped ?? 0,
        row.n_carried_forward ?? 0,
        row.calc_version ?? ""
      ].join(",")
    )
  );
  return new NextResponse(lines.join("\n") + "\n", {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Cache-Control": "public, max-age=3600",
      "Content-Disposition": `attachment; filename="${index.code}-history.csv"`,
      "X-Data-Source": "repo-managed-mvp-json"
    }
  });
}
