import { describe, expect, it } from "vitest";
import { cardCommerceQuery, commerceTargets } from "./commerce";

const card = {
  stable_variant_id: "cardmarket:onepiece:product:1:foil",
  name: "Roronoa Zoro",
  set_name: "Romance Dawn",
  collector_number: "OP01-001",
  tcgplayer_product_url: null
};

describe("commerce destinations", () => {
  it("builds an unambiguous marketplace query", () => {
    expect(cardCommerceQuery(card)).toBe("Roronoa Zoro OP01-001 Romance Dawn");
  });

  it("keeps marketplace destinations non-affiliate until templates are configured", () => {
    const targets = commerceTargets(card);

    expect(targets.map((target) => target.marketplace)).toEqual(["ebay", "tcgplayer"]);
    expect(targets.every((target) => target.affiliate === false)).toBe(true);
    expect(targets[0].href).toContain("ebay.de");
    expect(targets[1].href).toContain("tcgplayer.com");
  });
});
