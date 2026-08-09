"use client";

import { useMemo, useState } from "react";
import { activeConstituentsAsOf, constituentActions, filterConstituents } from "@/lib/constituents";
import type { Constituent } from "@/lib/types";

type Props = {
  constituents: Constituent[];
  initialAsOf: string;
  minDate: string;
  maxDate: string;
};

export function ConstituentsTable({ constituents, initialAsOf, minDate, maxDate }: Props) {
  const [asOf, setAsOf] = useState(initialAsOf);
  const [search, setSearch] = useState("");
  const [includeInactive, setIncludeInactive] = useState(false);
  const activeCount = useMemo(() => activeConstituentsAsOf(constituents, asOf).length, [asOf, constituents]);
  const visible = useMemo(
    () => filterConstituents(constituents, asOf, search, includeInactive),
    [asOf, constituents, includeInactive, search]
  );

  return (
    <div>
      <div className="mb-4 grid gap-3 sm:grid-cols-[220px_1fr_auto] sm:items-end">
        <label className="text-xs text-paper/55">
          As of
          <input
            type="date"
            min={minDate}
            max={maxDate}
            value={asOf}
            onChange={(event) => setAsOf(event.target.value)}
            className="surface mt-1 block w-full px-3 py-2 text-sm text-paper"
          />
        </label>
        <label className="text-xs text-paper/55">
          Search constituents
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Name, set, variant, or product ID"
            className="surface mt-1 block w-full px-3 py-2 text-sm text-paper placeholder:text-paper/30"
          />
        </label>
        <div className="flex flex-col gap-2 pb-2 text-xs text-paper/55">
          <label className="flex cursor-pointer items-center gap-2 whitespace-nowrap">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(event) => setIncludeInactive(event.target.checked)}
              className="h-4 w-4 accent-amber"
            />
            Include inactive
          </label>
          <span aria-live="polite">{activeCount} active / {visible.length} shown</span>
        </div>
      </div>

      <div className="surface overflow-x-auto">
        <table className="w-full min-w-[960px] border-collapse text-sm">
          <thead className="text-left text-paper/50">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Set</th>
              <th className="px-4 py-3">Variant</th>
              <th className="px-4 py-3">Member since</th>
              <th className="px-4 py-3">Action history</th>
              <th className="px-4 py-3 text-right">Liquidity</th>
              <th className="px-4 py-3 text-right">Ref price</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {visible.map((item) => {
              const inactive = Boolean(item.removed_at && item.removed_at <= asOf);
              return (
                <tr key={`${item.cm_product_id}-${item.variant_key}`} className={inactive ? "bg-paper/[0.02] text-paper/50" : undefined}>
                  <td className="px-4 py-3 text-paper">
                    <div>{item.name}</div>
                    <div className="mt-1 text-xs text-paper/35">CM {item.cm_product_id}</div>
                  </td>
                  <td className="px-4 py-3 text-paper/65">{item.set}</td>
                  <td className="px-4 py-3 text-paper/65">{item.variant_key}</td>
                  <td className="px-4 py-3 text-paper/65">{item.member_since}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {constituentActions(item).filter((event) => event.date <= asOf).map((event) => (
                        <span key={`${event.date}-${event.action}`} className="chip whitespace-nowrap">
                          {event.action} {event.date}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right text-paper/75">{item.liquidity_score.toFixed(3)}</td>
                  <td className="px-4 py-3 text-right text-paper/75">EUR {item.ref_price.toFixed(2)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {visible.length === 0 ? (
          <div className="border-t border-line px-4 py-10 text-center text-sm text-paper/50">
            No constituents match this date and search.
          </div>
        ) : null}
      </div>
    </div>
  );
}
