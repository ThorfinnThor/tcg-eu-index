import { describe, expect, it } from "vitest";
import { cardCommerceQuery, commerceTargets, tcgplayerCommerceQuery } from "./commerce";

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

  it("keeps disambiguating card text in TCGplayer searches", () => {
    expect(tcgplayerCommerceQuery({
      ...card,
      name: "Lugia EX [Aero Ball | Deep Hurricane]",
      set_name: "Expansion 1660",
      collector_number: null
    })).toBe("Lugia EX Aero Ball Deep Hurricane");
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
    expect(targets.map((target) => target.label)).toEqual(["eBay", "Search TCGplayer"]);
    expect(targets.map((target) => target.action)).toEqual(["search", "search"]);
    expect(targets.every((target) => target.affiliate === false)).toBe(true);
    expect(targets[0].href).toContain("ebay.de");
    expect(new URL(targets[0].href).searchParams.get("_nkw")).toBe(
      "Roronoa Zoro OP01-001 Romance Dawn One Piece card"
    );
    expect(targets[1].href).toContain("tcgplayer.com");
  });

  it("uses a verified TCGplayer product URL as a direct link", () => {
    const directUrl = "https://www.tcgplayer.com/product/123/roronoa-zoro";
    const target = commerceTargets({ ...card, tcgplayer_product_url: directUrl })[1];

    expect(target).toMatchObject({
      marketplace: "tcgplayer",
      label: "TCGplayer",
      href: directUrl,
      action: "open",
      affiliate: false
    });
  });
});
