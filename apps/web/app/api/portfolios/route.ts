import { NextResponse } from "next/server";
import { getIndexes } from "@/lib/data";
import { requestIp } from "@/lib/request-guards";
import { isRateLimited } from "@rate-limit";

export async function POST(request: Request) {
  if (await isRateLimited(`portfolio-create:${requestIp(request)}`)) {
    return NextResponse.json({ error: "Too many requests" }, { status: 429 });
  }
  const indexes = await getIndexes();
  if (!indexes.some((index) => index.status === "published" && index.history.length > 0)) {
    return NextResponse.json({ error: "Portfolio tools require published index data" }, { status: 409 });
  }
  const contentLength = Number(request.headers.get("content-length") ?? 0);
  if (contentLength > 2_048) return NextResponse.json({ error: "Request is too large" }, { status: 413 });
  const body = await request.json().catch(() => ({}));
  const name = typeof body.name === "string" ? body.name.trim().slice(0, 100) : "";
  const token = crypto.randomUUID().replaceAll("-", "");
  return NextResponse.json({
    public_token: token,
    name: name || "Untitled portfolio",
    created_at: new Date().toISOString(),
    storage: "client-session",
    mode: "json-only-mvp"
  });
}
