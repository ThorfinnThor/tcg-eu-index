import type { IndexCode } from "./types";

type PublicIndexDefinition = {
  legacyCode?: string;
  name: string;
  slug: string;
  targetSize: number;
};

export const publicIndexDefinitions: Record<IndexCode, PublicIndexDefinition> = {
  MTEU500: { name: "Magic Europe 500", slug: "magic-europe-500", targetSize: 500 },
  MTEUSLD: { name: "Magic Sealed Europe 100", slug: "magic-sealed-europe-100", targetSize: 100 },
  YGEU500: { legacyCode: "YGEU250", name: "Yu-Gi-Oh! Europe 500", slug: "yugioh-europe-500", targetSize: 500 },
  YGEUSLD: { name: "Yu-Gi-Oh! Sealed Europe 100", slug: "yugioh-sealed-europe-100", targetSize: 100 },
  OPEU500: { legacyCode: "OPEU100", name: "One Piece Europe 500", slug: "one-piece-europe-500", targetSize: 500 },
  OPEUSLD: { name: "One Piece Sealed Europe 100", slug: "one-piece-sealed-europe-100", targetSize: 100 },
  PKEU500: { legacyCode: "PKEU250", name: "Pokemon Europe 500", slug: "pokemon-europe-500", targetSize: 500 },
  PKEUSLD: { name: "Pokemon Sealed Europe 100", slug: "pokemon-sealed-europe-100", targetSize: 100 },
  DBSEU500: { legacyCode: "DBSEU100", name: "Dragon Ball Super Europe 500", slug: "dragon-ball-super-europe-500", targetSize: 500 },
  DBSEUSLD: { name: "Dragon Ball Super Sealed Europe 100", slug: "dragon-ball-super-sealed-europe-100", targetSize: 100 },
  FABEU500: { legacyCode: "FABEU100", name: "Flesh and Blood Europe 500", slug: "flesh-and-blood-europe-500", targetSize: 500 },
  FABEUSLD: { name: "Flesh and Blood Sealed Europe 100", slug: "flesh-and-blood-sealed-europe-100", targetSize: 100 },
  DGEU500: { legacyCode: "DGEU100", name: "Digimon Europe 500", slug: "digimon-europe-500", targetSize: 500 },
  DGEUSLD: { name: "Digimon Sealed Europe 100", slug: "digimon-sealed-europe-100", targetSize: 100 },
  LCEU500: { legacyCode: "LCEU100", name: "Disney Lorcana Europe 500", slug: "disney-lorcana-europe-500", targetSize: 500 },
  LCEUSLD: { name: "Disney Lorcana Sealed Europe 100", slug: "disney-lorcana-sealed-europe-100", targetSize: 100 },
  SWUEU500: { legacyCode: "SWUEU100", name: "Star Wars Unlimited Europe 500", slug: "star-wars-unlimited-europe-500", targetSize: 500 },
  SWUEUSLD: { name: "Star Wars Unlimited Sealed Europe 100", slug: "star-wars-unlimited-sealed-europe-100", targetSize: 100 },
  RBEU500: { legacyCode: "RBEU100", name: "Riftbound Europe 500", slug: "riftbound-europe-500", targetSize: 500 },
  RBEUSLD: { name: "Riftbound Sealed Europe 100", slug: "riftbound-sealed-europe-100", targetSize: 100 }
};

const currentByLegacy = Object.fromEntries(
  Object.entries(publicIndexDefinitions)
    .filter(([, definition]) => definition.legacyCode)
    .map(([code, definition]) => [definition.legacyCode, code])
) as Record<string, IndexCode>;

export function canonicalIndexCode(code: string): string {
  return currentByLegacy[code] ?? code;
}

export function indexAssetCandidates(code: string): string[] {
  const canonical = canonicalIndexCode(code) as IndexCode;
  const legacy = publicIndexDefinitions[canonical]?.legacyCode;
  return [...new Set([canonical, legacy, code].filter((value): value is string => Boolean(value)))];
}

export function applyPublicIndexMetadata<T extends { code: string; name: string; slug: string; target_size: number }>(record: T): T {
  const code = canonicalIndexCode(record.code) as IndexCode;
  const definition = publicIndexDefinitions[code];
  if (!definition) return record;
  return {
    ...record,
    code,
    name: definition.name,
    slug: definition.slug,
    target_size: definition.targetSize
  };
}

export function applyPublicSearchMetadata<
  T extends { id: IndexCode; name: string; slug: string; filterValues: { target_size: number } }
>(record: T): T {
  const id = canonicalIndexCode(record.id) as IndexCode;
  const definition = publicIndexDefinitions[id];
  if (!definition) return record;
  return {
    ...record,
    id,
    name: definition.name,
    slug: definition.slug,
    filterValues: { ...record.filterValues, target_size: definition.targetSize }
  };
}
