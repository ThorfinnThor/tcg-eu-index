"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { cardmarketProductUrl } from "@/lib/cardmarket";
import { affiliateCommerceConfigured, commerceTargets } from "@/lib/commerce";
import {
  cardImageDeliveryUrl,
  formatCollectorEur,
  matchesCollectorPriceBand,
  type CollectorPriceBand
} from "@/lib/collector-ui";
import type {
  CollectorCompositionIndex,
  CollectorCompositionPage,
  CollectorRebalanceRecord
} from "@/lib/types";

type Props = {
  composition: CollectorCompositionIndex;
  compositionPage: CollectorCompositionPage;
  gameName: string;
};

type Member = CollectorRebalanceRecord["constituents"][number];
const resultPageSize = 250;
const noMembers: Member[] = [];
const supportedImageHosts = new Set([
  "product-images.s3.cardmarket.com",
  "cards.scryfall.io",
  "images.pokemontcg.io",
  "images.ygoprodeck.com",
  "product-images.tcgplayer.com",
  "assets.tcgdex.net",
  "cards.lorcast.io",
  "cdn.swu-db.com",
  "images.digimoncard.io",
  "storage.googleapis.com",
  "legendstory-production-s3-public.s3.amazonaws.com",
  "d2wlb52bya4y8z.cloudfront.net",
  "cmsassets.rgpub.io",
  "en.onepiece-cardgame.com",
  "tcg-eu-index-web.shuu9599.workers.dev",
]);
const providerAttributions: Record<string, { name: string; url: string }> = {
  tcgdex: { name: "TCGdex / Pokemon TCG API", url: "https://pokemontcg.io/" },
  ygoprodeck: { name: "YGOPRODeck", url: "https://ygoprodeck.com/" },
  digimon: { name: "DigimonCard.io", url: "https://digimoncard.io/" },
  lorcast: { name: "Lorcast", url: "https://lorcast.com/" },
  swudb: { name: "SWU DB", url: "https://www.swu-db.com/" },
  fab_dataset: {
    name: "Flesh and Blood Cards",
    url: "https://github.com/the-fab-cube/flesh-and-blood-cards"
  },
  riot_riftbound: {
    name: "Riot Games Riftbound Card Gallery",
    url: "https://playriftbound.com/en-us/card-gallery/"
  },
  bandai_onepiece: {
    name: "ONE PIECE CARD GAME Official Card List",
    url: "https://en.onepiece-cardgame.com/cardlist/"
  },
};

const priceBands: Array<{ value: CollectorPriceBand; label: string }> = [
  { value: "all", label: "All prices from €10" },
  { value: "10-100", label: "€10–100" },
  { value: "100-1000", label: "€100–1,000" },
  { value: "1000-10000", label: "€1,000–10,000" },
  { value: "10000-plus", label: "€10,000+" }
];

function matchesSearch(member: Member, query: string) {
  if (!query) return true;
  return [
    member.name,
    member.set_name,
    member.set_code,
    member.collector_number,
    String(member.cm_product_id),
    member.variant_key,
    member.stable_variant_id,
  ].some((value) => value?.toLocaleLowerCase().includes(query));
}

function displaySetName(value: string | null) {
  if (!value || /^Expansion\s+\d+$/iu.test(value.trim())) return "Set details pending";
  return value;
}

function byAscendingPrice(left: Member, right: Member) {
  return left.selection_price - right.selection_price
    || left.stable_variant_id.localeCompare(right.stable_variant_id);
}

function supportedImageUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && supportedImageHosts.has(url.hostname) ? value : null;
  } catch {
    return null;
  }
}

async function loadWholeIndex(
  code: string,
  effectiveDate: string,
  pages: Array<{ path: string }>,
  signal: AbortSignal
) {
  const members: Member[] = [];
  const batchSize = 8;
  for (let start = 0; start < pages.length; start += batchSize) {
    const batch = await Promise.all(
      pages.slice(start, start + batchSize).map(async (page) => {
        const response = await fetch(`/data/collector/${code}/${page.path}`, { signal });
        if (!response.ok) throw new Error(`Could not load composition page ${page.path}`);
        const payload = await response.json() as CollectorCompositionPage;
        if (payload.effective_date !== effectiveDate || !Array.isArray(payload.constituents)) {
          throw new Error(`Composition page ${page.path} has invalid data`);
        }
        return payload.constituents;
      })
    );
    for (const pageMembers of batch) members.push(...pageMembers);
  }
  return members;
}

function CardArtwork({ member }: { member: Member }) {
  const structuredImage = member.image;
  const publishable = structuredImage?.status === "exact" || structuredImage?.status === "manual";
  const preferredUrl = publishable ? structuredImage.front?.normal?.url ?? null : null;
  const imageUrl = supportedImageUrl(
    cardImageDeliveryUrl(preferredUrl ?? (structuredImage ? null : member.image_url))
  );
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const visibleUrl = imageUrl === failedUrl ? null : imageUrl;
  const setLabel = displaySetName(member.set_name);
  const altParts = [member.name];
  if (setLabel !== "Set details pending") altParts.push(setLabel);
  if (member.collector_number) altParts.push(member.collector_number);
  if (
    structuredImage?.artwork_variant
    && structuredImage.artwork_variant !== "base"
    && structuredImage.artwork_variant !== "unknown"
  ) {
    altParts.push(structuredImage.artwork_variant.replaceAll("_", " "));
  }
  const placeholder = failedUrl || structuredImage?.status === "provider_error"
    ? "Image unavailable"
    : "Image not assigned";
  return (
    <div className="relative aspect-[488/680] w-12 shrink-0 overflow-hidden rounded border border-line bg-ink/70">
      {visibleUrl ? (
        <Image
          src={visibleUrl}
          alt={altParts.join(" – ")}
          fill
          sizes="48px"
          className="object-contain"
          unoptimized
          onError={() => setFailedUrl(visibleUrl)}
        />
      ) : (
        <div className="flex h-full items-center justify-center px-1 text-center text-[9px] leading-3 text-paper/30">
          {placeholder}
        </div>
      )}
    </div>
  );
}

export function CollectorCompositionTable({ composition, compositionPage, gameName }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [priceBand, setPriceBand] = useState<CollectorPriceBand>("all");
  const [resultPage, setResultPage] = useState(1);
  const [loadedIndex, setLoadedIndex] = useState<{ key: string; members: Member[] } | null>(null);
  const [loadErrorKey, setLoadErrorKey] = useState<string | null>(null);
  const deferredSearch = useDeferredValue(search);
  const selectedRebalance = useMemo(
    () => composition.rebalances.find(
      (rebalance) => rebalance.effective_date === compositionPage.effective_date
    ) ?? composition.rebalances.at(-1)
      ?? null,
    [composition.rebalances, compositionPage.effective_date]
  );
  const query = deferredSearch.trim().toLocaleLowerCase();
  const wholeIndexMode = priceBand !== "all" || query.length > 0;
  const selectionKey = selectedRebalance
    ? `${composition.index_code}:${selectedRebalance.effective_date}`
    : "none";

  useEffect(() => {
    if (!wholeIndexMode || !selectedRebalance || loadedIndex?.key === selectionKey) return;
    const controller = new AbortController();
    loadWholeIndex(
      composition.index_code,
      selectedRebalance.effective_date,
      selectedRebalance.pages,
      controller.signal
    ).then((members) => {
      setLoadedIndex({ key: selectionKey, members });
      setLoadErrorKey(null);
    }).catch((error: unknown) => {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setLoadErrorKey(selectionKey);
    });
    return () => controller.abort();
  }, [composition.index_code, loadedIndex?.key, selectedRebalance, selectionKey, wholeIndexMode]);

  const wholeIndexReady = loadedIndex?.key === selectionKey;
  const wholeIndexError = loadErrorKey === selectionKey;
  const sourceMembers = wholeIndexMode
    ? (wholeIndexReady ? loadedIndex.members : noMembers)
    : compositionPage.constituents;
  const filteredMembers = useMemo(
    () => sourceMembers
      .filter(
        (member) => matchesCollectorPriceBand(member.selection_price, priceBand) && matchesSearch(member, query)
      )
      .sort(byAscendingPrice),
    [priceBand, query, sourceMembers]
  );

  if (!selectedRebalance) {
    return <p className="py-8 text-sm text-paper/50">No card list is available yet.</p>;
  }

  const resultPageCount = Math.max(1, Math.ceil(filteredMembers.length / resultPageSize));
  const visibleMembers = wholeIndexMode
    ? filteredMembers.slice((resultPage - 1) * resultPageSize, resultPage * resultPageSize)
    : filteredMembers;

  const resultSummary = wholeIndexMode
    ? wholeIndexError
      ? "Could not load the full card list"
      : !wholeIndexReady
        ? `Searching all ${selectedRebalance.active_count.toLocaleString("en-GB")} cards…`
        : `${filteredMembers.length.toLocaleString("en-GB")} cards found`
    : `${visibleMembers.length.toLocaleString("en-GB")} shown · ${selectedRebalance.active_count.toLocaleString("en-GB")} total`;
  const showsScryfallImages = visibleMembers.some((member) =>
    member.image?.provider === "scryfall"
    && (member.image.status === "exact" || member.image.status === "manual")
  );
  const visibleProviderAttributions = [...new Set(
    visibleMembers
      .filter((member) => member.image?.status === "exact" || member.image?.status === "manual")
      .map((member) => member.image?.provider)
      .filter((provider): provider is string => Boolean(provider && provider !== "scryfall"))
  )]
    .map((provider) => providerAttributions[provider])
    .filter((provider): provider is { name: string; url: string } => Boolean(provider));

  return (
    <div>
      <div className="mb-4 grid gap-3 lg:grid-cols-[180px_220px_1fr_auto] lg:items-end">
        <label className="text-xs text-paper/55">
          Card list from
          <select
            value={selectedRebalance.effective_date}
            onChange={(event) => {
              setResultPage(1);
              setLoadErrorKey(null);
              router.push(`${pathname}?date=${encodeURIComponent(event.target.value)}&page=1`);
            }}
            className="surface mt-1 block w-full px-3 py-2 text-sm text-paper"
          >
            {composition.rebalances.map((rebalance) => (
              <option key={rebalance.effective_date} value={rebalance.effective_date}>
                {rebalance.effective_date}
              </option>
            ))}
          </select>
        </label>

        <label className="text-xs text-paper/55">
          Price range
          <select
            value={priceBand}
            onChange={(event) => {
              setPriceBand(event.target.value as CollectorPriceBand);
              setResultPage(1);
              setLoadErrorKey(null);
            }}
            className="surface mt-1 block w-full px-3 py-2 text-sm text-paper"
          >
            {priceBands.map((band) => (
              <option key={band.value} value={band.value}>{band.label}</option>
            ))}
          </select>
        </label>

        <label className="text-xs text-paper/55">
          Search the entire index
          <input
            type="search"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setResultPage(1);
              setLoadErrorKey(null);
            }}
            placeholder="Card name, set, number, variant, or Cardmarket ID"
            className="surface mt-1 block w-full px-3 py-2 text-sm text-paper placeholder:text-paper/30"
          />
        </label>

        <div className="pb-2 text-xs text-paper/55" aria-live="polite">{resultSummary}</div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2 text-xs text-paper/50">
        <span className="chip">Cards priced from €10</span>
        <span className="chip">Basket updated monthly</span>
        <span className="chip">Foil and nonfoil shown separately</span>
      </div>

      {showsScryfallImages ? (
        <p className="mb-4 border-l-2 border-amber/70 pl-3 text-xs leading-5 text-paper/55">
          Card imagery and metadata provided by <a href="https://scryfall.com" target="_blank" rel="noopener noreferrer" className="text-amber hover:text-paper">Scryfall</a>. TCG EU Index is unofficial Fan Content permitted under the Fan Content Policy. Not approved or endorsed by Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.
        </p>
      ) : null}

      {visibleProviderAttributions.map((provider) => (
        <p key={provider.name} className="mb-4 border-l-2 border-amber/70 pl-3 text-xs leading-5 text-paper/55">
          Card imagery and metadata provided by <a href={provider.url} target="_blank" rel="noopener noreferrer" className="text-amber hover:text-paper">{provider.name}</a>. Card names and artwork belong to their respective rights holders. TCG EU Index is unofficial and is not endorsed by the game publisher.
        </p>
      ))}

      {affiliateCommerceConfigured() ? (
        <p className="mb-4 border-l-2 border-amber/70 pl-3 text-xs leading-5 text-paper/55">
          Some marketplace links are affiliate links. TCG EU Index may receive a commission at no additional cost to the buyer. Marketplace availability and prices are independent from the index calculation.
        </p>
      ) : null}

      {wholeIndexMode && !wholeIndexReady ? (
        <div className="surface px-4 py-10 text-center text-sm text-paper/55">
          {wholeIndexError
            ? "The full card list could not be loaded. Clear the filter and try again."
            : "Loading the full index for this search…"}
        </div>
      ) : (
        <div className="surface overflow-x-auto">
          <table className="w-full min-w-[980px] border-collapse text-sm">
            <thead className="text-left text-paper/50">
              <tr>
                <th className="px-4 py-3">Card</th>
                <th className="px-4 py-3">Set</th>
                <th className="px-4 py-3">Variant</th>
                <th className="px-4 py-3 text-right">30-day average price</th>
                <th className="px-4 py-3">Marketplaces</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {visibleMembers.map((member) => (
                <tr key={member.stable_variant_id}>
                  <td className="px-4 py-3 text-paper">
                    <div className="flex items-center gap-3">
                      <CardArtwork member={member} />
                      <div className="min-w-0">
                        <a
                          href={cardmarketProductUrl(gameName, member.cm_product_id, member.variant_key)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-medium hover:text-amber"
                          aria-label={`Open ${member.name} on Cardmarket`}
                        >
                          {member.name} <span aria-hidden="true">↗</span>
                        </a>
                        <span className="mt-1 block text-xs text-paper/40">
                          {member.collector_number ? `No. ${member.collector_number} · ` : ""}
                          {member.set_code ? `Set ${member.set_code} · ` : ""}
                          CM {member.cm_product_id}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-paper/65">{displaySetName(member.set_name)}</td>
                  <td className="px-4 py-3 text-paper/70">{member.variant_key}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-paper/80">
                    {formatCollectorEur(member.selection_price)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      <a
                        href={cardmarketProductUrl(gameName, member.cm_product_id, member.variant_key)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="chip hover:border-amber hover:text-amber"
                        aria-label={`Open ${member.name} on Cardmarket`}
                      >
                        Cardmarket
                      </a>
                      {commerceTargets(member, gameName).map((target) => (
                        <a
                          key={target.marketplace}
                          href={target.href}
                          target="_blank"
                          rel={target.affiliate ? "sponsored nofollow noopener noreferrer" : "noopener noreferrer"}
                          className="chip hover:border-amber hover:text-amber"
                          aria-label={`${target.action === "open" ? "Open" : "Search for"} ${member.name} on ${target.marketplace === "tcgplayer" ? "TCGplayer" : target.label}${target.affiliate ? " (affiliate link)" : ""}`}
                        >
                          {target.label}{target.affiliate ? " · Ad" : ""}
                        </a>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {visibleMembers.length === 0 ? (
            <div className="border-t border-line px-4 py-8 text-center text-sm text-paper/50">
              No cards match these filters.
            </div>
          ) : null}
        </div>
      )}

      {wholeIndexMode && wholeIndexReady && resultPageCount > 1 ? (
        <nav className="mt-4 flex items-center justify-between gap-4 text-xs text-paper/55" aria-label="Filtered result pages">
          <button
            type="button"
            disabled={resultPage === 1}
            onClick={() => setResultPage((page) => Math.max(1, page - 1))}
            className="chip disabled:opacity-35"
          >
            Previous
          </button>
          <span>Results page {resultPage} of {resultPageCount}</span>
          <button
            type="button"
            disabled={resultPage === resultPageCount}
            onClick={() => setResultPage((page) => Math.min(resultPageCount, page + 1))}
            className="chip disabled:opacity-35"
          >
            Next
          </button>
        </nav>
      ) : null}

      {!wholeIndexMode && selectedRebalance.page_count > 1 ? (
        <nav className="mt-4 flex items-center justify-between gap-4 text-xs text-paper/55" aria-label="Composition pages">
          {compositionPage.page > 1 ? (
            <Link
              href={`${pathname}?date=${encodeURIComponent(selectedRebalance.effective_date)}&page=${compositionPage.page - 1}`}
              className="chip"
            >
              Previous
            </Link>
          ) : <span className="chip opacity-35">Previous</span>}
          <span>Page {compositionPage.page} of {selectedRebalance.page_count}</span>
          {compositionPage.page < selectedRebalance.page_count ? (
            <Link
              href={`${pathname}?date=${encodeURIComponent(selectedRebalance.effective_date)}&page=${compositionPage.page + 1}`}
              className="chip"
            >
              Next
            </Link>
          ) : <span className="chip opacity-35">Next</span>}
        </nav>
      ) : null}

      <p className="mt-3 text-xs leading-5 text-paper/45">
        Card names and sets come from the Cardmarket catalogue. Images are shown only when a licensed or permitted source is available. Foil and nonfoil variants count as separate cards when both meet the €10 rule.
      </p>
    </div>
  );
}
