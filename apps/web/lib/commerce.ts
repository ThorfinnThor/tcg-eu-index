export type CommerceCard = {
  stable_variant_id: string;
  name: string;
  set_name: string | null;
  set_code?: string | null;
  collector_number: string | null;
  tcgplayer_product_url: string | null;
};

export type CommerceTarget = {
  marketplace: "ebay" | "tcgplayer";
  label: string;
  href: string;
  affiliate: boolean;
  action: "open" | "search";
};

const ebayAffiliateTemplate = process.env.NEXT_PUBLIC_EBAY_AFFILIATE_URL_TEMPLATE;
const tcgplayerAffiliateTemplate = process.env.NEXT_PUBLIC_TCGPLAYER_AFFILIATE_URL_TEMPLATE;

export function cardCommerceQuery(card: CommerceCard): string {
  const name = card.name
    .replace(/(?:\s*\[[^\]]*\])+\s*$/u, "")
    .replace(/\s+/gu, " ")
    .trim();
  const setName = card.set_name && !/^Expansion\s+\d+$/iu.test(card.set_name.trim())
    ? card.set_name.trim()
    : null;
  const collectorNumber = card.collector_number?.trim() || null;
  const setCode = card.set_code?.trim() || null;
  const distinctSetCode = setCode && collectorNumber
    && collectorNumber.toLocaleLowerCase().startsWith(setCode.toLocaleLowerCase())
    ? null
    : setCode;

  return [name, distinctSetCode, collectorNumber, setName]
    .filter((value): value is string => Boolean(value))
    .join(" ");
}

export function tcgplayerCommerceQuery(card: CommerceCard): string {
  const name = card.name
    .replace(/[\[\]|]/gu, " ")
    .replace(/\s+/gu, " ")
    .trim();
  const setName = card.set_name && !/^Expansion\s+\d+$/iu.test(card.set_name.trim())
    ? card.set_name.trim()
    : null;
  const collectorNumber = card.collector_number?.trim() || null;
  const setCode = card.set_code?.trim() || null;
  const distinctSetCode = setCode && collectorNumber
    && collectorNumber.toLocaleLowerCase().startsWith(setCode.toLocaleLowerCase())
    ? null
    : setCode;

  return [name, distinctSetCode, collectorNumber, setName]
    .filter((value): value is string => Boolean(value))
    .join(" ");
}

export function commerceTargets(card: CommerceCard, gameName?: string): CommerceTarget[] {
  const query = cardCommerceQuery(card);
  const customId = card.stable_variant_id.replaceAll(":", "-").slice(0, 256);
  const ebayDestination = new URL("https://www.ebay.de/sch/i.html");
  ebayDestination.searchParams.set(
    "_nkw",
    [query, gameName, gameName ? "card" : null].filter(Boolean).join(" "),
  );
  const tcgplayerDestination = card.tcgplayer_product_url
    ? new URL(card.tcgplayer_product_url)
    : new URL("https://www.tcgplayer.com/search/all/product");
  if (!card.tcgplayer_product_url) {
    tcgplayerDestination.searchParams.set("q", tcgplayerCommerceQuery(card));
    tcgplayerDestination.searchParams.set("view", "grid");
  }

  return [
    target(
      "ebay",
      "eBay",
      ebayDestination.toString(),
      ebayAffiliateTemplate,
      customId,
      "search",
    ),
    target(
      "tcgplayer",
      card.tcgplayer_product_url ? "TCGplayer" : "Search TCGplayer",
      tcgplayerDestination.toString(),
      tcgplayerAffiliateTemplate,
      customId,
      card.tcgplayer_product_url ? "open" : "search",
    ),
  ];
}

export function affiliateCommerceConfigured(): boolean {
  return Boolean(ebayAffiliateTemplate || tcgplayerAffiliateTemplate);
}

function target(
  marketplace: CommerceTarget["marketplace"],
  label: string,
  destination: string,
  template: string | undefined,
  customId: string,
  action: CommerceTarget["action"],
): CommerceTarget {
  if (!template) return { marketplace, label, href: destination, affiliate: false, action };
  const href = template
    .replaceAll("{url}", encodeURIComponent(destination))
    .replaceAll("{custom_id}", encodeURIComponent(customId));
  const parsed = new URL(href);
  if (parsed.protocol !== "https:") {
    throw new Error(`${marketplace} affiliate template must produce an HTTPS URL`);
  }
  return { marketplace, label, href: parsed.toString(), affiliate: true, action };
}
