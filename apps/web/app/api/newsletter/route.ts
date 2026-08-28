import { NextResponse } from "next/server";
import { z } from "zod";
import { requestIp } from "@/lib/request-guards";
import { isRateLimited } from "@rate-limit";

const signupSchema = z.object({
  email: z.string().trim().email().max(254),
  consent: z.literal(true)
});
function providerUrl() {
  const configured = process.env.NEWSLETTER_ENDPOINT;
  if (!configured) return null;
  const url = new URL(configured);
  if (url.protocol !== "https:" || ["localhost", "127.0.0.1", "::1"].includes(url.hostname)) {
    throw new Error("NEWSLETTER_ENDPOINT must be a public HTTPS URL");
  }
  return url;
}

export async function POST(request: Request) {
  const endpoint = providerUrl();
  if (!endpoint) {
    return NextResponse.json({ error: "Newsletter signup is not configured" }, { status: 503 });
  }
  if (await isRateLimited(`newsletter:${requestIp(request)}`, 5)) {
    return NextResponse.json({ error: "Too many signup attempts" }, { status: 429 });
  }
  const contentLength = Number(request.headers.get("content-length") ?? 0);
  if (contentLength > 2_048) {
    return NextResponse.json({ error: "Request is too large" }, { status: 413 });
  }
  const parsed = signupSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: "A valid email and consent are required" }, { status: 400 });
  }

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (process.env.NEWSLETTER_API_KEY) {
    headers.Authorization = `Token ${process.env.NEWSLETTER_API_KEY}`;
  }
  const response = await fetch(endpoint, {
    method: "POST",
    headers,
    body: JSON.stringify({
      email_address: parsed.data.email,
      metadata: { source: "tcg-eu-index-reports" }
    }),
    cache: "no-store"
  });
  if (!response.ok) {
    return NextResponse.json({ error: "Newsletter provider rejected the signup" }, { status: 502 });
  }
  return NextResponse.json({ ok: true });
}
