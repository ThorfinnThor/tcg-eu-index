import { describe, expect, it } from "vitest";
import { parsePortfolioCsv } from "./portfolio";

describe("parsePortfolioCsv", () => {
  it("parses valid holdings and defaults variant", () => {
    const rows = parsePortfolioCsv("cm_product_id,variant_key,quantity,cost_basis_eur\n750123,,3,12.50\n");
    expect(rows[0]).toMatchObject({ ok: true, holding: { variant_key: "nonfoil", quantity: 3 } });
  });

  it("reports invalid rows", () => {
    const rows = parsePortfolioCsv("cm_product_id,variant_key,quantity\nbad,nonfoil,0\n");
    expect(rows[0]).toMatchObject({ ok: false, line: 2 });
  });
});
