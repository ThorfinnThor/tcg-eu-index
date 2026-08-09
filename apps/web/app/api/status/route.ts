import { NextResponse } from "next/server";
import { getStatus } from "@/lib/data";

export const revalidate = 3600;

export async function GET() {
  return NextResponse.json(await getStatus(), {
    headers: { "Cache-Control": "public, max-age=3600, stale-while-revalidate=86400" }
  });
}
