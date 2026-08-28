import { describe, expect, it } from "vitest";
import { cardmarketProductUrl } from "./cardmarket";

describe("Cardmarket product links", () => {
  it.each([
    ["Magic: The Gathering", "Magic"],
    ["Yu-Gi-Oh!", "YuGiOh"],
    ["One Piece", "OnePiece"],
    ["Pokemon", "Pokemon"],
    ["Dragon Ball Super", "DragonBallSuper"],
    ["Flesh and Blood", "FleshAndBlood"],
    ["Digimon", "Digimon"],
    ["Disney Lorcana", "Lorcana"],
    ["Star Wars: Unlimited", "StarWarsUnlimited"],
    ["Riftbound", "Riftbound"]
  ])("builds a stable %s product redirect", (game, segment) => {
    expect(cardmarketProductUrl(game, 123456)).toBe(
      `https://www.cardmarket.com/en/${segment}/Products?idProduct=123456`
    );
  });

  it("filters a product page to the indexed foil variant", () => {
    expect(cardmarketProductUrl("Pokemon", 284277, "foil")).toBe(
      "https://www.cardmarket.com/en/Pokemon/Products?idProduct=284277&isFoil=Y"
    );
  });

  it("rejects unsupported games and invalid IDs", () => {
    expect(() => cardmarketProductUrl("Unknown", 1)).toThrow("Unsupported Cardmarket game");
    expect(() => cardmarketProductUrl("One Piece", 0)).toThrow("Invalid Cardmarket product ID");
  });
});
