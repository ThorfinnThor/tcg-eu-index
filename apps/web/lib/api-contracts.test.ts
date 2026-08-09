import { describe, expect, it } from "vitest";
import { GET as getStatus } from "../app/api/status/route";
import { POST as createPortfolio } from "../app/api/portfolios/route";
import { PUT as uploadHoldings } from "../app/api/portfolios/[token]/holdings/route";
import { GET as comparePortfolio } from "../app/api/portfolios/[token]/vs/[code]/route";
import { GET as downloadHistory } from "../app/api/public/[code]/history.csv/route";

describe("public API contracts", () => {
  it("returns status freshness with cache headers", async () => {
    const response = await getStatus();
    const payload = await response.json();
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toContain("max-age=3600");
    expect(payload).toMatchObject({
      source: "repo-managed-mvp-json",
      dataset_version: expect.any(String),
      generated_at: expect.any(String),
      gap_count: expect.any(Number),
      indexes: expect.any(Array)
    });
  });

  it("creates an explicitly stateless MVP portfolio token", async () => {
    const request = new Request("http://localhost/api/portfolios", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Collector test" })
    });
    const response = await createPortfolio(request);
    const payload = await response.json();
    expect(payload).toMatchObject({ name: "Collector test", mode: "json-only-mvp", storage: "client-session" });
    expect(payload.public_token).toMatch(/^[a-f0-9]{32}$/);
  });

  it("validates uploaded CSV and reports unmatched rows", async () => {
    const csv = [
      "cm_product_id,variant_key,quantity,cost_basis_eur",
      "750001,nonfoil,2,3",
      "999999,nonfoil,1,4"
    ].join("\n");
    const response = await uploadHoldings(new Request("http://localhost", { method: "PUT", body: csv }), {
      params: { token: "contract-token" }
    });
    const payload = await response.json();
    expect(payload).toMatchObject({ token: "contract-token", accepted: 1, mode: "json-only-mvp" });
    expect(payload.errors).toHaveLength(1);
    expect(payload.holdings).toHaveLength(1);
  });

  it("returns the benchmark contract and rejects unknown codes", async () => {
    const valid = await comparePortfolio(new Request("http://localhost"), {
      params: { token: "contract-token", code: "OPEU100" }
    });
    expect(await valid.json()).toMatchObject({ token: "contract-token", code: "OPEU100", mode: "stateless-benchmark-only" });

    const missing = await comparePortfolio(new Request("http://localhost"), {
      params: { token: "contract-token", code: "UNKNOWN" }
    });
    expect(missing.status).toBe(404);
  });

  it("downloads auditable index history as CSV", async () => {
    const response = await downloadHistory(new Request("http://localhost"), { params: { code: "OPEU100" } });
    const body = await response.text();
    expect(response.status).toBe(200);
    expect(response.headers.get("content-disposition")).toContain("OPEU100-history.csv");
    expect(response.headers.get("x-data-source")).toBe("repo-managed-mvp-json");
    expect(body.split("\n")[0]).toBe(
      "value_date,index_value,daily_return,n_constituents_active,n_capped,n_carried_forward,calc_version"
    );

    const missing = await downloadHistory(new Request("http://localhost"), { params: { code: "UNKNOWN" } });
    expect(missing.status).toBe(404);
  });
});
