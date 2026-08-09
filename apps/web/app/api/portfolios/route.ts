import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const token = crypto.randomUUID().replaceAll("-", "");
  return NextResponse.json({
    public_token: token,
    name: body.name || "Untitled portfolio",
    created_at: new Date().toISOString()
  });
}
