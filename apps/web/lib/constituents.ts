import type { Constituent, IndexCode, RebalanceHistory, RebalanceRecord } from "./types";

export type ConstituentAction = {
  date: string;
  action: Constituent["action"];
};

export function constituentActions(item: Constituent): ConstituentAction[] {
  const actions: ConstituentAction[] = [{ date: item.member_since, action: "added" }];
  if (item.removed_at) actions.push({ date: item.removed_at, action: "removed" });
  return actions.sort((left, right) => left.date.localeCompare(right.date));
}

export function activeConstituentsAsOf(constituents: Constituent[], asOf: string) {
  return constituents.filter((item) => item.member_since <= asOf && (!item.removed_at || item.removed_at > asOf));
}

export function filterConstituents(constituents: Constituent[], asOf: string, search: string, includeInactive = false) {
  const query = search.trim().toLocaleLowerCase();
  const available = includeInactive
    ? constituents.filter((item) => item.member_since <= asOf)
    : activeConstituentsAsOf(constituents, asOf);
  return available.filter((item) => {
    if (!query) return true;
    return [item.name, item.set, item.variant_key, String(item.cm_product_id)]
      .some((value) => value.toLocaleLowerCase().includes(query));
  });
}

export function latestCompositionDate(constituents: Constituent[], fallback: string) {
  return constituents.reduce((latest, item) => {
    const lifecycleLatest = item.removed_at && item.removed_at > item.member_since ? item.removed_at : item.member_since;
    return lifecycleLatest > latest ? lifecycleLatest : latest;
  }, fallback);
}

export function constituentKey(item: Pick<Constituent, "cm_product_id" | "variant_key">) {
  return `${item.cm_product_id}:${item.variant_key}`;
}

export type CompositionDelta = {
  additions: Constituent[];
  removals: Constituent[];
  retained: Constituent[];
};

export function compositionDelta(constituents: Constituent[], from: string, to: string): CompositionDelta {
  const fromMembers = new Map(activeConstituentsAsOf(constituents, from).map((item) => [constituentKey(item), item]));
  const toMembers = new Map(activeConstituentsAsOf(constituents, to).map((item) => [constituentKey(item), item]));
  const byName = (left: Constituent, right: Constituent) => left.name.localeCompare(right.name);
  return {
    additions: [...toMembers].filter(([key]) => !fromMembers.has(key)).map(([, item]) => item).sort(byName),
    removals: [...fromMembers].filter(([key]) => !toMembers.has(key)).map(([, item]) => item).sort(byName),
    retained: [...toMembers].filter(([key]) => fromMembers.has(key)).map(([, item]) => item).sort(byName)
  };
}

export function compositionDates(constituents: Constituent[], fallback: string) {
  return [...new Set([
    fallback,
    ...constituents.flatMap((item) => [item.member_since, item.removed_at].filter((value): value is string => Boolean(value)))
  ])].sort();
}

export function deriveRebalanceHistory(
  code: IndexCode,
  constituents: Constituent[],
  dataState: RebalanceHistory["data_state"],
  generatedFor: string,
  methodologyVersion = "1.3.0"
): RebalanceHistory {
  const dates = compositionDates(constituents, constituents[0]?.member_since ?? generatedFor);
  const rebalances = dates.map<RebalanceRecord>((effectiveDate, index) => {
    const additions = constituents.filter((item) => item.member_since === effectiveDate);
    const removals = constituents.filter((item) => item.removed_at === effectiveDate);
    const active = activeConstituentsAsOf(constituents, effectiveDate);
    return {
      effective_date: effectiveDate,
      methodology_version: methodologyVersion,
      selection_snapshot_sha256: null,
      eligible_count: null,
      active_count: active.length,
      retained_count: Math.max(active.length - additions.length, 0),
      changes: [
        ...additions.map((item) => ({
          cm_product_id: item.cm_product_id,
          variant_key: item.variant_key,
          action: "added" as const,
          reason: item.entry_reason ?? (index === 0 ? "Initial composition" : "Entered the selection")
        })),
        ...removals.map((item) => ({
          cm_product_id: item.cm_product_id,
          variant_key: item.variant_key,
          action: "removed" as const,
          reason: item.removal_reason ?? "Left the selection"
        }))
      ]
    };
  });
  return {
    schema_version: 1,
    index_code: code,
    data_state: dataState,
    cadence: "monthly",
    generated_for: generatedFor,
    rebalances
  };
}

function isoWeek(dateValue: string) {
  const value = new Date(`${dateValue}T00:00:00Z`);
  const day = value.getUTCDay() || 7;
  value.setUTCDate(value.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(value.getUTCFullYear(), 0, 1));
  const week = Math.ceil((((value.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
  return `${value.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

export type RebalanceGroup = {
  key: string;
  records: RebalanceRecord[];
  additions: number;
  removals: number;
  retained: number;
};

export function groupRebalances(records: RebalanceRecord[], period: "week" | "month"): RebalanceGroup[] {
  const grouped = new Map<string, RebalanceRecord[]>();
  for (const record of records) {
    const key = period === "week" ? isoWeek(record.effective_date) : record.effective_date.slice(0, 7);
    grouped.set(key, [...(grouped.get(key) ?? []), record]);
  }
  return [...grouped.entries()].map(([key, groupedRecords]) => ({
    key,
    records: groupedRecords.sort((left, right) => right.effective_date.localeCompare(left.effective_date)),
    additions: groupedRecords.reduce((sum, record) => sum + record.changes.filter((change) => change.action === "added").length, 0),
    removals: groupedRecords.reduce((sum, record) => sum + record.changes.filter((change) => change.action === "removed").length, 0),
    retained: groupedRecords.reduce((sum, record) => sum + record.retained_count, 0)
  })).sort((left, right) => right.key.localeCompare(left.key));
}
