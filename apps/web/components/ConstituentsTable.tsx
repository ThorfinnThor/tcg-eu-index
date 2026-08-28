"use client";

import { useEffect, useMemo, useState } from "react";
import {
  activeConstituentsAsOf,
  compositionDates,
  compositionDelta,
  constituentActions,
  constituentKey,
  filterConstituents,
  groupRebalances
} from "@/lib/constituents";
import type { Constituent, RebalanceChange, RebalanceHistory, RebalanceRecord } from "@/lib/types";

type Props = {
  constituents: Constituent[];
  rebalances: RebalanceHistory;
  initialAsOf: string;
  initialSearch: string;
  initialIncludeInactive: boolean;
  minDate: string;
  maxDate: string;
  targetSize: number;
};

function findChangedConstituent(constituents: Constituent[], change: RebalanceChange, record: RebalanceRecord) {
  return constituents.find((item) =>
    constituentKey(item) === `${change.cm_product_id}:${change.variant_key}` &&
    (change.action === "added" ? item.member_since === record.effective_date : item.removed_at === record.effective_date)
  ) ?? constituents.find((item) => constituentKey(item) === `${change.cm_product_id}:${change.variant_key}`);
}

function ChangeList({
  title,
  items,
  tone
}: {
  title: string;
  items: Constituent[];
  tone: "mint" | "coral";
}) {
  return (
    <section className="border-t border-line pt-4">
      <div className="mb-3 flex items-center justify-between gap-4">
        <h3 className="text-sm font-medium text-paper">{title}</h3>
        <span className={tone === "mint" ? "text-sm text-mint" : "text-sm text-coral"}>{items.length}</span>
      </div>
      {items.length ? (
        <ul className="divide-y divide-line text-sm">
          {items.map((item) => (
            <li key={`${constituentKey(item)}:${item.member_since}`} className="flex items-start justify-between gap-4 py-3">
              <div className="min-w-0">
                <div className="truncate text-paper">{item.name}</div>
                <div className="mt-1 truncate text-xs text-paper/45">{item.set}</div>
              </div>
              <span className="shrink-0 text-xs text-paper/45">{item.variant_key}</span>
            </li>
          ))}
        </ul>
      ) : <p className="py-5 text-sm text-paper/45">No cards in this category.</p>}
    </section>
  );
}

function periodLabel(key: string, period: "week" | "month") {
  if (period === "week") return `Week ${key.slice(-2)}, ${key.slice(0, 4)}`;
  return new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" })
    .format(new Date(`${key}-01T00:00:00Z`));
}

export function ConstituentsTable({
  constituents,
  rebalances,
  initialAsOf,
  initialSearch,
  initialIncludeInactive,
  minDate,
  maxDate,
  targetSize
}: Props) {
  const [view, setView] = useState<"composition" | "changes">("composition");
  const [period, setPeriod] = useState<"week" | "month">("month");
  const [asOf, setAsOf] = useState(initialAsOf);
  const [search, setSearch] = useState(initialSearch);
  const [includeInactive, setIncludeInactive] = useState(initialIncludeInactive);
  const dates = useMemo(() => compositionDates(constituents, minDate), [constituents, minDate]);
  const [compareFrom, setCompareFrom] = useState(dates[0] ?? minDate);
  const [compareTo, setCompareTo] = useState(dates.at(-1) ?? maxDate);
  const activeCount = useMemo(() => activeConstituentsAsOf(constituents, asOf).length, [asOf, constituents]);
  const visible = useMemo(
    () => filterConstituents(constituents, asOf, search, includeInactive),
    [asOf, constituents, includeInactive, search]
  );
  const delta = useMemo(() => compositionDelta(constituents, compareFrom, compareTo), [compareFrom, compareTo, constituents]);
  const groups = useMemo(() => groupRebalances(rebalances.rebalances, period), [period, rebalances.rebalances]);
  const isPreview = rebalances.cadence === "daily_preview";

  useEffect(() => {
    if (view !== "composition") return;
    const params = new URLSearchParams({ asOf });
    if (search.trim()) params.set("q", search.trim());
    if (includeInactive) params.set("inactive", "1");
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, [asOf, includeInactive, search, view]);

  return (
    <div>
      <div className="mb-6 flex border-b border-line" role="tablist" aria-label="Constituent views">
        {(["composition", "changes"] as const).map((item) => (
          <button
            key={item}
            type="button"
            role="tab"
            aria-selected={view === item}
            onClick={() => setView(item)}
            className={`border-b-2 px-4 py-3 text-sm capitalize transition-colors ${
              view === item ? "border-amber text-paper" : "border-transparent text-paper/50 hover:text-paper/80"
            }`}
          >
            {item === "composition" ? "Composition" : "Changes"}
          </button>
        ))}
      </div>

      {view === "composition" ? (
        <div role="tabpanel">
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
              <span aria-live="polite">{activeCount} active / {targetSize} target</span>
            </div>
          </div>

          <div className="surface overflow-x-auto">
            <table className="w-full min-w-[1020px] border-collapse text-sm">
              <thead className="text-left text-paper/50">
                <tr>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Set</th>
                  <th className="px-4 py-3">Variant</th>
                  <th className="px-4 py-3">Member since</th>
                  <th className="px-4 py-3">Action history</th>
                  <th className="px-4 py-3 text-right">Ref. price</th>
                  <th className="px-4 py-3 text-right">Liquidity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {visible.map((item) => {
                  const inactive = Boolean(item.removed_at && item.removed_at <= asOf);
                  return (
                    <tr key={`${constituentKey(item)}:${item.member_since}`} className={inactive ? "bg-paper/[0.02] text-paper/50" : undefined}>
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
                      <td className="px-4 py-3 text-right text-paper/75">EUR {item.ref_price.toFixed(2)}</td>
                      <td className="px-4 py-3 text-right text-paper/75">{item.liquidity_score.toFixed(3)}</td>
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
      ) : (
        <div role="tabpanel" className="space-y-10">
          <section>
            <div className="mb-5 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
              <div>
                <h2 className="text-lg font-medium">Compare composition dates</h2>
                <p className="mt-1 text-sm text-paper/50">See exactly which cards entered, left, or remained between two snapshots.</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <label className="text-xs text-paper/55">
                  From
                  <select
                    value={compareFrom}
                    onChange={(event) => {
                      setCompareFrom(event.target.value);
                      if (event.target.value > compareTo) setCompareTo(event.target.value);
                    }}
                    className="surface mt-1 block w-full min-w-36 px-3 py-2 text-sm text-paper"
                  >
                    {dates.map((date) => <option key={date}>{date}</option>)}
                  </select>
                </label>
                <label className="text-xs text-paper/55">
                  To
                  <select
                    value={compareTo}
                    onChange={(event) => setCompareTo(event.target.value)}
                    className="surface mt-1 block w-full min-w-36 px-3 py-2 text-sm text-paper"
                  >
                    {dates.filter((date) => date >= compareFrom).map((date) => <option key={date}>{date}</option>)}
                  </select>
                </label>
              </div>
            </div>
            <div className="grid grid-cols-3 border-y border-line py-4 text-center">
              <div><div className="text-xl font-semibold text-mint">+{delta.additions.length}</div><div className="mt-1 text-xs text-paper/45">Added</div></div>
              <div className="border-x border-line"><div className="text-xl font-semibold text-coral">-{delta.removals.length}</div><div className="mt-1 text-xs text-paper/45">Removed</div></div>
              <div><div className="text-xl font-semibold text-paper">{delta.retained.length}</div><div className="mt-1 text-xs text-paper/45">Retained</div></div>
            </div>
            <div className="mt-6 grid gap-8 md:grid-cols-2">
              <ChangeList title="Added cards" items={delta.additions} tone="mint" />
              <ChangeList title="Removed cards" items={delta.removals} tone="coral" />
            </div>
          </section>

          <section>
            <div className="mb-5 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
              <div>
                <h2 className="text-lg font-medium">Rebalance history</h2>
                <p className="mt-1 max-w-2xl text-sm leading-6 text-paper/50">
                  {isPreview
                    ? "Preview composition is recalculated daily. Weekly and monthly views group the actual provisional additions and removals."
                    : "The official methodology rebalances monthly. Weekly view groups actual events by calendar week; weeks without a rebalance have no membership changes."}
                </p>
              </div>
              <div className="surface inline-flex self-start p-1" aria-label="History grouping">
                {(["week", "month"] as const).map((item) => (
                  <button
                    key={item}
                    type="button"
                    aria-pressed={period === item}
                    onClick={() => setPeriod(item)}
                    className={`min-w-20 px-3 py-1.5 text-xs capitalize ${period === item ? "bg-paper/10 text-paper" : "text-paper/45"}`}
                  >
                    {item === "week" ? "Weekly" : "Monthly"}
                  </button>
                ))}
              </div>
            </div>
            <div className="divide-y divide-line border-y border-line">
              {groups.map((group) => (
                <section key={group.key} className="py-5">
                  <div className="flex flex-wrap items-baseline justify-between gap-3">
                    <h3 className="font-medium text-paper">{periodLabel(group.key, period)}</h3>
                    <div className="flex gap-4 text-xs">
                      <span className="text-mint">+{group.additions} added</span>
                      <span className="text-coral">-{group.removals} removed</span>
                      <span className="text-paper/50">{group.retained} retained</span>
                    </div>
                  </div>
                  {group.records.map((record) => (
                    <details key={record.effective_date} className="mt-4 border-t border-line/60 pt-4" open={group === groups[0]}>
                      <summary className="cursor-pointer text-sm text-paper/70">
                        Effective {record.effective_date} · {record.active_count} active · methodology {record.methodology_version}
                      </summary>
                      <div className="mt-3 divide-y divide-line/60">
                        {record.changes.map((change) => {
                          const item = findChangedConstituent(constituents, change, record);
                          return (
                            <div key={`${change.action}:${change.cm_product_id}:${change.variant_key}`} className="grid gap-1 py-3 text-sm sm:grid-cols-[90px_1fr_1fr] sm:gap-4">
                              <span className={change.action === "added" ? "text-mint" : "text-coral"}>{change.action}</span>
                              <span className="text-paper">{item?.name ?? `CM ${change.cm_product_id}`} <span className="text-paper/40">({change.variant_key})</span></span>
                              <span className="text-paper/50">{change.reason}</span>
                            </div>
                          );
                        })}
                        {record.changes.length === 0 ? <p className="py-3 text-sm text-paper/45">No additions or removals.</p> : null}
                      </div>
                    </details>
                  ))}
                </section>
              ))}
              {groups.length === 0 ? <p className="py-8 text-sm text-paper/45">No rebalance history is available yet.</p> : null}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
