import type { DailyIndexValue } from "./types";

export type ChartRange = "1M" | "3M" | "6M" | "1Y" | "Max";

export type IndexAnalytics = {
  startDate: string | null;
  endDate: string | null;
  observationCount: number;
  periodReturn: number;
  maxDrawdown: number;
  bestDay: DailyIndexValue | null;
  worstDay: DailyIndexValue | null;
  positiveDayRatio: number;
  annualizedVolatility30d: number;
  cappedDays: number;
  carriedForwardDays: number;
};

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

function annualizedVolatility(rows: DailyIndexValue[]) {
  if (rows.length < 2) return 0;
  const returns = rows.map((row) => row.daily_return);
  const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
  const variance = returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / returns.length;
  return Math.sqrt(variance) * Math.sqrt(365);
}

export function calculateIndexAnalytics(history: DailyIndexValue[]): IndexAnalytics {
  if (history.length === 0) {
    return {
      startDate: null,
      endDate: null,
      observationCount: 0,
      periodReturn: 0,
      maxDrawdown: 0,
      bestDay: null,
      worstDay: null,
      positiveDayRatio: 0,
      annualizedVolatility30d: 0,
      cappedDays: 0,
      carriedForwardDays: 0
    };
  }

  const first = history[0];
  const last = history.at(-1) ?? first;
  const bestDay = history.reduce((best, row) => row.daily_return > best.daily_return ? row : best, first);
  const worstDay = history.reduce((worst, row) => row.daily_return < worst.daily_return ? row : worst, first);
  const positiveDays = history.filter((row) => row.daily_return > 0).length;
  const drawdowns = chartPoints(history).map((point) => point.drawdown / 100);

  return {
    startDate: first.value_date,
    endDate: last.value_date,
    observationCount: history.length,
    periodReturn: last.index_value / first.index_value - 1,
    maxDrawdown: Math.min(...drawdowns),
    bestDay,
    worstDay,
    positiveDayRatio: positiveDays / history.length,
    annualizedVolatility30d: annualizedVolatility(history.slice(-30)),
    cappedDays: history.filter((row) => (row.n_capped ?? 0) > 0).length,
    carriedForwardDays: history.filter((row) => (row.n_carried_forward ?? 0) > 0).length
  };
}
