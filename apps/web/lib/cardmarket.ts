const gameSegments: Record<string, string> = {
  "Magic: The Gathering": "Magic",
  "Yu-Gi-Oh!": "YuGiOh",
  "One Piece": "OnePiece",
  Pokemon: "Pokemon",
  "Dragon Ball Super": "DragonBallSuper",
  "Flesh and Blood": "FleshAndBlood",
  Digimon: "Digimon",
  "Disney Lorcana": "Lorcana",
  "Star Wars: Unlimited": "StarWarsUnlimited",
  Riftbound: "Riftbound"
};

export function cardmarketProductUrl(game: string, productId: number, variantKey?: string) {
  const segment = gameSegments[game];
  if (!segment) throw new Error(`Unsupported Cardmarket game: ${game}`);
  if (!Number.isSafeInteger(productId) || productId <= 0) {
    throw new Error(`Invalid Cardmarket product ID: ${productId}`);
  }

  const url = new URL(`https://www.cardmarket.com/en/${segment}/Products`);
  url.searchParams.set("idProduct", String(productId));
  if (variantKey === "foil") url.searchParams.set("isFoil", "Y");
  return url.toString();
}
