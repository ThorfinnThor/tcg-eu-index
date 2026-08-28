import { describe, expect, it } from "vitest";
import { GET as getStatus } from "../app/api/status/route";
import { POST as createPortfolio } from "../app/api/portfolios/route";
import { PUT as uploadHoldings } from "../app/api/portfolios/[token]/holdings/route";
import { GET as comparePortfolio } from "../app/api/portfolios/[token]/vs/[code]/route";
import { GET as downloadHistory } from "../app/api/public/[code]/history.csv/route";

describe("public API contracts", () => {
  const token = "0123456789abcdef0123456789abcdef";
  it("returns status freshness with cache headers", async () => {
    const response = await getStatus();
    const payload = await response.json();
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toContain("max-age=3600");
    expect(payload).toMatchObject({
      source: "cardmarket-derived-preview-json",
      dataset_version: expect.any(String),
      generated_at: expect.any(String),
      gap_count: expect.any(Number),
      indexes: expect.any(Array)
    });
  });

  it("keeps portfolio creation unavailable before index publication", async () => {
    const request = new Request("http://localhost/api/portfolios", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Collector test" })
    });
    const response = await createPortfolio(request);
    const payload = await response.json();
    expect(response.status).toBe(409);
    expect(payload).toEqual({ error: "Portfolio tools require published index data" });
  });

  it("keeps portfolio matching unavailable before index publication", async () => {
    const csv = [
      "cm_product_id,variant_key,quantity,cost_basis_eur",
      "750001,nonfoil,2,3",
      "999999,nonfoil,1,4"
    ].join("\n");
    const response = await uploadHoldings(new Request("http://localhost", { method: "PUT", body: csv }), {
      params: Promise.resolve({ token })
    });
    const payload = await response.json();
    expect(response.status).toBe(409);
    expect(payload).toEqual({ error: "Portfolio matching requires published index data" });
  });

  it("rejects unpublished and unknown benchmark comparisons", async () => {
    const valid = await comparePortfolio(new Request("http://localhost"), {
      params: Promise.resolve({ token, code: "OPEU100" })
    });
    expect(valid.status).toBe(409);
    expect(await valid.json()).toEqual({ error: "Benchmark has not been published" });

    const missing = await comparePortfolio(new Request("http://localhost"), {
      params: Promise.resolve({ token, code: "UNKNOWN" })
    });
    expect(missing.status).toBe(404);
  });

  it("exposes labelled preview history through the public CSV route", async () => {
    const response = await downloadHistory(new Request("http://localhost"), {
      params: Promise.resolve({ code: "OPEU100" })
    });
    expect(response.status).toBe(200);
    expect(response.headers.get("x-index-status")).toBe("preview");
    expect(response.headers.get("x-preview-warning")).toBe("Provisional-not-official-not-investment-advice");
    expect(await response.text()).toMatch(/^value_date,index_value,daily_return/);

    const missing = await downloadHistory(new Request("http://localhost"), {
      params: Promise.resolve({ code: "UNKNOWN" })
    });
    expect(missing.status).toBe(404);
  });
});
