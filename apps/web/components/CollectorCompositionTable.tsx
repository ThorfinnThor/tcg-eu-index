"use client";

import { useMemo, useState } from "react";
import { cardmarketProductUrl } from "@/lib/cardmarket";
import type { CollectorRebalanceRecord, CollectorRebalances } from "@/lib/types";
import { formatCollectorEur } from "@/lib/collector-ui";

type Props = {
  rebalances: CollectorRebalances;
  gameName: string;
};

function matchesSearch(member: CollectorRebalanceRecord["constituents"][number], query: string) {
  if (!query) return true;
  return [String(member.cm_product_id), member.variant_key, member.stable_variant_id]
    .some((value) => value.toLocaleLowerCase().includes(query));
}

export function CollectorCompositionTable({ rebalances, gameName }: Props) {
  const [selectedDate, setSelectedDate] = useState(rebalances.rebalances.at(-1)?.effective_date ?? "");
  const [search, setSearch] = useState("");
  const selectedRebalance = useMemo(
    () => rebalances.rebalances.find((rebalance) => rebalance.effective_date === selectedDate)
      ?? rebalances.rebalances.at(-1)
      ?? null,
    [rebalances.rebalances, selectedDate]
  );
  const query = search.trim().toLocaleLowerCase();
  const visibleMembers = useMemo(
    () => selectedRebalance?.constituents.filter((member) => matchesSearch(member, query)) ?? [],
    [query, selectedRebalance]
  );

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
            onChange={(event) => setSelectedDate(event.target.value)}
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
          Search variants
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Cardmarket ID, variant, or stable ID"
            className="surface mt-1 block w-full px-3 py-2 text-sm text-paper placeholder:text-paper/30"
          />
        </label>
        <div className="pb-2 text-xs text-paper/55" aria-live="polite">
          {visibleMembers.length} of {selectedRebalance.constituents.length} variants
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2 text-xs text-paper/50">
        <span className="chip">Selection as of {selectedRebalance.selection_as_of}</span>
        <span className="chip">{selectedRebalance.active_count} active variants</span>
        <span className="chip">No target size</span>
      </div>

      <div className="surface overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-sm">
          <thead className="text-left text-paper/50">
            <tr>
              <th className="px-4 py-3">Cardmarket article</th>
              <th className="px-4 py-3">Variant</th>
              <th className="px-4 py-3">Stable variant ID</th>
              <th className="px-4 py-3 text-right">Selection AVG30</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {visibleMembers.map((member) => (
              <tr key={member.stable_variant_id}>
                <td className="px-4 py-3 text-paper">
                  <a
                    href={cardmarketProductUrl(gameName, member.cm_product_id, member.variant_key)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:text-amber"
                    aria-label={`Open Cardmarket product ${member.cm_product_id}`}
                  >
                    Cardmarket product {member.cm_product_id} <span aria-hidden="true">↗</span>
                  </a>
                  <span className="mt-1 block text-xs text-paper/35">ID {member.cm_product_id}</span>
                </td>
                <td className="px-4 py-3 text-paper/70">{member.variant_key}</td>
                <td className="px-4 py-3 font-mono text-xs text-paper/45">{member.stable_variant_id}</td>
                <td className="px-4 py-3 text-right tabular-nums text-paper/80">
                  {formatCollectorEur(member.selection_price)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {visibleMembers.length === 0 ? (
          <div className="border-t border-line px-4 py-8 text-center text-sm text-paper/50">
            No variants match this search.
          </div>
        ) : null}
      </div>
      <p className="mt-3 text-xs leading-5 text-paper/45">
        The v1.5 output contract currently exposes Cardmarket product IDs and variants, not catalogue names or set labels. Both foil and nonfoil are displayed independently when they are separate eligible variants.
      </p>
    </div>
  );
}
