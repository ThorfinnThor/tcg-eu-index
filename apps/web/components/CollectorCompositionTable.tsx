"use client";

import Image from "next/image";
import { useDeferredValue, useMemo, useState } from "react";
import { cardmarketProductUrl } from "@/lib/cardmarket";
import { affiliateCommerceConfigured, commerceTargets } from "@/lib/commerce";
import type { CollectorRebalanceRecord, CollectorRebalances } from "@/lib/types";
import { formatCollectorEur } from "@/lib/collector-ui";

type Props = {
  rebalances: CollectorRebalances;
  gameName: string;
};

type Member = CollectorRebalanceRecord["constituents"][number];

const PAGE_SIZE = 100;
const supportedImageHosts = new Set([
  "product-images.s3.cardmarket.com",
  "cards.scryfall.io",
  "images.pokemontcg.io",
  "images.ygoprodeck.com",
  "product-images.tcgplayer.com",
]);

function matchesSearch(member: Member, query: string) {
  if (!query) return true;
  return [
    member.name,
    member.set_name,
    member.collector_number,
    String(member.cm_product_id),
    member.variant_key,
    member.stable_variant_id,
  ].some((value) => value?.toLocaleLowerCase().includes(query));
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

function CardArtwork({ member }: { member: Member }) {
  const imageUrl = supportedImageUrl(member.image_url);
  return (
    <div className="relative h-[68px] w-12 shrink-0 overflow-hidden rounded border border-line bg-ink/70">
      {imageUrl ? (
        <Image
          src={imageUrl}
          alt={`${member.name} card artwork`}
          fill
          sizes="48px"
          className="object-cover"
          unoptimized
        />
      ) : (
        <div className="flex h-full items-center justify-center px-1 text-center text-[9px] leading-3 text-paper/30">
          Image pending
        </div>
      )}
    </div>
  );
}

export function CollectorCompositionTable({ rebalances, gameName }: Props) {
  const [selectedDate, setSelectedDate] = useState(rebalances.rebalances.at(-1)?.effective_date ?? "");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const deferredSearch = useDeferredValue(search);
  const selectedRebalance = useMemo(
    () => rebalances.rebalances.find((rebalance) => rebalance.effective_date === selectedDate)
      ?? rebalances.rebalances.at(-1)
      ?? null,
    [rebalances.rebalances, selectedDate]
  );
  const query = deferredSearch.trim().toLocaleLowerCase();
  const filteredMembers = useMemo(
    () => selectedRebalance?.constituents.filter((member) => matchesSearch(member, query)) ?? [],
    [query, selectedRebalance]
  );
  const pageCount = Math.max(1, Math.ceil(filteredMembers.length / PAGE_SIZE));
  const visibleMembers = filteredMembers.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  if (!selectedRebalance) {
    return <p className="py-8 text-sm text-paper/50">No monthly composition is available yet.</p>;
  }

  return (
    <div>
      <div className="mb-4 grid gap-3 sm:grid-cols-[220px_1fr_auto] sm:items-end">
        <label className="text-xs text-paper/55">
          Composition effective
          <select
            value={selectedRebalance.effective_date}
            onChange={(event) => {
              setSelectedDate(event.target.value);
              setPage(1);
            }}
            className="surface mt-1 block w-full px-3 py-2 text-sm text-paper"
          >
            {rebalances.rebalances.map((rebalance) => (
              <option key={rebalance.effective_date} value={rebalance.effective_date}>
                {rebalance.effective_date}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-paper/55">
          Search cards
          <input
            type="search"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
            placeholder="Card name, set, number, variant, or Cardmarket ID"
            className="surface mt-1 block w-full px-3 py-2 text-sm text-paper placeholder:text-paper/30"
          />
        </label>
        <div className="pb-2 text-xs text-paper/55" aria-live="polite">
          {filteredMembers.length} of {selectedRebalance.constituents.length} variants
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2 text-xs text-paper/50">
        <span className="chip">Selection as of {selectedRebalance.selection_as_of}</span>
        <span className="chip">{selectedRebalance.active_count} active variants</span>
        <span className="chip">No target size</span>
        <span className="chip">AVG30 ≥ €10</span>
      </div>

      {affiliateCommerceConfigured() ? (
        <p className="mb-4 border-l-2 border-amber/70 pl-3 text-xs leading-5 text-paper/55">
          Some marketplace links are affiliate links. TCG EU Index may receive a commission at no additional cost to the buyer. Marketplace availability and prices are independent from the index calculation.
        </p>
      ) : null}

      <div className="surface overflow-x-auto">
        <table className="w-full min-w-[980px] border-collapse text-sm">
          <thead className="text-left text-paper/50">
            <tr>
              <th className="px-4 py-3">Card</th>
              <th className="px-4 py-3">Set</th>
              <th className="px-4 py-3">Variant</th>
              <th className="px-4 py-3 text-right">Selection AVG30</th>
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
                        {member.collector_number ? `No. ${member.collector_number} · ` : ""}CM {member.cm_product_id}
                      </span>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3 text-paper/65">
                  {member.set_name ?? "Set metadata pending"}
                </td>
                <td className="px-4 py-3 text-paper/70">{member.variant_key}</td>
                <td className="px-4 py-3 text-right tabular-nums text-paper/80">
                  {formatCollectorEur(member.selection_price)}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    {commerceTargets(member).map((target) => (
                      <a
                        key={target.marketplace}
                        href={target.href}
                        target="_blank"
                        rel={target.affiliate ? "sponsored nofollow noopener noreferrer" : "noopener noreferrer"}
                        className="chip hover:border-amber hover:text-amber"
                        aria-label={`Search for ${member.name} on ${target.label}${target.affiliate ? " (affiliate link)" : ""}`}
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
        {filteredMembers.length === 0 ? (
          <div className="border-t border-line px-4 py-8 text-center text-sm text-paper/50">
            No variants match this search.
          </div>
        ) : null}
      </div>

      {filteredMembers.length > PAGE_SIZE ? (
        <nav className="mt-4 flex items-center justify-between gap-4 text-xs text-paper/55" aria-label="Composition pages">
          <button
            type="button"
            onClick={() => setPage((value) => Math.max(1, value - 1))}
            disabled={page === 1}
            className="chip disabled:cursor-not-allowed disabled:opacity-35"
          >
            Previous
          </button>
          <span>Page {page} of {pageCount}</span>
          <button
            type="button"
            onClick={() => setPage((value) => Math.min(pageCount, value + 1))}
            disabled={page === pageCount}
            className="chip disabled:cursor-not-allowed disabled:opacity-35"
          >
            Next
          </button>
        </nav>
      ) : null}

      <p className="mt-3 text-xs leading-5 text-paper/45">
        Card names and sets come from the official Cardmarket catalogue. Collector numbers are shown only when an explicit source value is available. Images require a licensed or explicitly permitted metadata source and otherwise remain marked as pending. Foil and nonfoil are independent index constituents when both qualify.
      </p>
    </div>
  );
}
