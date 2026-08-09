import type { DailyIndexValue } from "./types";

export type ChartRange = "1M" | "3M" | "6M" | "1Y" | "Max";

const rangeDays: Record<Exclude<ChartRange, "Max">, number> = {
  "1M": 30,
  "3M": 90,
  "6M": 180,
  "1Y": 365
};

export function historyForRange(history: DailyIndexValue[], range: ChartRange) {
  if (range === "Max" || history.length === 0) return history;
  const latest = new Date(`${history.at(-1)?.value_date}T00:00:00Z`);
  const cutoff = new Date(latest);
  cutoff.setUTCDate(cutoff.getUTCDate() - rangeDays[range]);
  const cutoffDate = cutoff.toISOString().slice(0, 10);
  return history.filter((row) => row.value_date >= cutoffDate);
}

export function chartPoints(history: DailyIndexValue[]) {
  let runningPeak = Number.NEGATIVE_INFINITY;
  return history.map((row) => {
    runningPeak = Math.max(runningPeak, row.index_value);
    return {
      date: row.value_date,
      label: row.value_date.slice(5),
      value: Number(row.index_value.toFixed(2)),
      drawdown: Number(((row.index_value / runningPeak - 1) * 100).toFixed(2))
    };
  });
}
