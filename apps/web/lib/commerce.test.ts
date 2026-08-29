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

  it("removes attack text and internal expansion placeholders", () => {
    expect(cardCommerceQuery({
      ...card,
      name: "Lugia EX [Aero Ball | Deep Hurricane]",
      set_name: "Expansion 1660",
      collector_number: null
    })).toBe("Lugia EX");
  });

  it("keeps a real collector number while removing internal metadata", () => {
    expect(cardCommerceQuery({
      ...card,
      name: "Primal Groudon EX [Gaia Volcano]",
      set_name: "Expansion 1660",
      collector_number: "XY7-86"
    })).toBe("Primal Groudon EX XY7-86");
  });

  it("keeps marketplace destinations non-affiliate until templates are configured", () => {
    const targets = commerceTargets(card, "One Piece");

    expect(targets.map((target) => target.marketplace)).toEqual(["ebay", "tcgplayer"]);
    expect(targets.every((target) => target.affiliate === false)).toBe(true);
    expect(targets[0].href).toContain("ebay.de");
    expect(new URL(targets[0].href).searchParams.get("_nkw")).toBe(
      "Roronoa Zoro OP01-001 Romance Dawn One Piece card"
    );
    expect(targets[1].href).toContain("tcgplayer.com");
  });
});
