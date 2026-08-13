import { afterEach, describe, expect, it, vi } from "vitest";
import { POST } from "@/app/api/newsletter/route";

const originalEndpoint = process.env.NEWSLETTER_ENDPOINT;
const originalApiKey = process.env.NEWSLETTER_API_KEY;

afterEach(() => {
  vi.unstubAllGlobals();
  if (originalEndpoint === undefined) delete process.env.NEWSLETTER_ENDPOINT;
  else process.env.NEWSLETTER_ENDPOINT = originalEndpoint;
  if (originalApiKey === undefined) delete process.env.NEWSLETTER_API_KEY;
  else process.env.NEWSLETTER_API_KEY = originalApiKey;
});

describe("newsletter route", () => {
  it("stays unavailable until a provider is configured", async () => {
    delete process.env.NEWSLETTER_ENDPOINT;
    const response = await POST(new Request("http://localhost/api/newsletter", { method: "POST" }));
    expect(response.status).toBe(503);
  });

  it("validates consent before contacting the provider", async () => {
    process.env.NEWSLETTER_ENDPOINT = "https://newsletter.example/subscribers";
    const provider = vi.fn();
    vi.stubGlobal("fetch", provider);
    const response = await POST(new Request("http://localhost/api/newsletter", {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-forwarded-for": "198.51.100.1" },
      body: JSON.stringify({ email: "reader@example.com", consent: false })
    }));
    expect(response.status).toBe(400);
    expect(provider).not.toHaveBeenCalled();
  });

  it("forwards an explicitly consented signup without exposing the API key", async () => {
    process.env.NEWSLETTER_ENDPOINT = "https://newsletter.example/subscribers";
    process.env.NEWSLETTER_API_KEY = "private-token";
    const provider = vi.fn().mockResolvedValue(new Response(null, { status: 201 }));
    vi.stubGlobal("fetch", provider);
    const response = await POST(new Request("http://localhost/api/newsletter", {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-forwarded-for": "198.51.100.2" },
      body: JSON.stringify({ email: "reader@example.com", consent: true })
    }));
    expect(response.status).toBe(200);
    expect(provider).toHaveBeenCalledWith(
      new URL("https://newsletter.example/subscribers"),
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ Authorization: "Token private-token" })
      })
    );
    expect(await response.text()).not.toContain("private-token");
  });
});
