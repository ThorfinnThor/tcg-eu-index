import type { Constituent } from "./types";

export type ConstituentAction = {
  date: string;
  action: Constituent["action"];
};

export function constituentActions(item: Constituent): ConstituentAction[] {
  const firstAction = item.action === "removed" ? "added" : item.action;
  const actions: ConstituentAction[] = [{ date: item.member_since, action: firstAction }];
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
