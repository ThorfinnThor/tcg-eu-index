export type FreshnessLevel = "fresh" | "delayed" | "stale" | "unknown";

export type Freshness = {
  level: FreshnessLevel;
  ageDays: number | null;
  label: string;
};

export function assessFreshness(latestDate: string | null, now = new Date()): Freshness {
  if (!latestDate || Number.isNaN(Date.parse(`${latestDate}T00:00:00Z`))) {
    return { level: "unknown", ageDays: null, label: "Freshness unknown" };
  }
  const currentDate = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const snapshotDate = Date.parse(`${latestDate}T00:00:00Z`);
  if (snapshotDate > currentDate) {
    return { level: "unknown", ageDays: null, label: "Future-dated snapshot" };
  }
  const ageDays = Math.max(0, Math.floor((currentDate - snapshotDate) / 86_400_000));
  if (ageDays <= 2) return { level: "fresh", ageDays, label: ageDays === 0 ? "Current today" : `${ageDays} day${ageDays === 1 ? "" : "s"} old` };
  if (ageDays <= 7) return { level: "delayed", ageDays, label: `${ageDays} days old` };
  return { level: "stale", ageDays, label: `${ageDays} days old` };
}

export function freshnessClass(level: FreshnessLevel) {
  if (level === "fresh") return `border-teal ${freshnessTextClass(level)}`;
  if (level === "delayed") return `border-amber ${freshnessTextClass(level)}`;
  if (level === "stale") return `border-coral ${freshnessTextClass(level)}`;
  return "border-line text-paper/60";
}

export function freshnessTextClass(level: FreshnessLevel) {
  if (level === "fresh") return "text-teal";
  if (level === "delayed") return "text-amber";
  if (level === "stale") return "text-coral";
  return "text-paper/60";
}
