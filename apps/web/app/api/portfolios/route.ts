import { NextResponse } from "next/server";
import { getIndexes } from "@/lib/data";

export async function POST(request: Request) {
  const indexes = await getIndexes();
  if (!indexes.some((index) => index.status === "published" && index.history.length > 0)) {
    return NextResponse.json({ error: "Portfolio tools require published index data" }, { status: 409 });
  }
  const body = await request.json().catch(() => ({}));
  const token = crypto.randomUUID().replaceAll("-", "");
  return NextResponse.json({
    public_token: token,
    name: body.name || "Untitled portfolio",
    created_at: new Date().toISOString(),
    storage: "client-session",
    mode: "json-only-mvp"
  });
}
