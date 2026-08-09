"use client";

import { useId, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { chartPoints, historyForRange, type ChartRange } from "@/lib/index-analytics";
import type { DailyIndexValue } from "@/lib/types";

function HistoryChart({ history, compact, drawdown }: { history: DailyIndexValue[]; compact: boolean; drawdown: boolean }) {
  const gradientId = `chart-fill-${useId().replaceAll(":", "")}`;
  const data = useMemo(() => chartPoints(history), [history]);
  const dataKey = drawdown ? "drawdown" : "value";
  return (
    <div className={compact ? "h-28" : "h-80"}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ left: 0, right: 8, top: 10, bottom: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={drawdown ? "#e87967" : "#e7b75f"} stopOpacity={0.45} />
              <stop offset="95%" stopColor={drawdown ? "#e87967" : "#e7b75f"} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#34342e" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: "#a7a195", fontSize: 12 }} tickLine={false} axisLine={false} />
          <YAxis
            tick={{ fill: "#a7a195", fontSize: 12 }}
            tickFormatter={(value) => drawdown ? `${value}%` : String(value)}
            tickLine={false}
            axisLine={false}
            width={54}
          />
          <Tooltip
            contentStyle={{ background: "#191916", border: "1px solid #34342e", borderRadius: 8 }}
            labelStyle={{ color: "#f4efe4" }}
            labelFormatter={(_, payload) => payload?.[0]?.payload?.date ?? ""}
            formatter={(value: number) => [drawdown ? `${value.toFixed(2)}%` : value.toFixed(2), drawdown ? "Drawdown" : "Index"]}
          />
          <Area
            type="monotone"
            dataKey={dataKey}
            stroke={drawdown ? "#e87967" : "#e7b75f"}
            strokeWidth={2}
            fill={`url(#${gradientId})`}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function IndexChart({ history, compact = false }: { history: DailyIndexValue[]; compact?: boolean }) {
  return <HistoryChart history={history} compact={compact} drawdown={false} />;
}

const ranges: ChartRange[] = ["1M", "3M", "6M", "1Y", "Max"];

export function IndexChartExplorer({ history }: { history: DailyIndexValue[] }) {
  const [range, setRange] = useState<ChartRange>("3M");
  const [drawdown, setDrawdown] = useState(false);
  const visibleHistory = useMemo(() => historyForRange(history, range), [history, range]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex rounded border border-line p-1" aria-label="Chart range">
          {ranges.map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={range === option}
              onClick={() => setRange(option)}
              className={`min-w-10 rounded px-2 py-1 text-xs ${range === option ? "bg-amber font-semibold text-ink" : "text-paper/65 hover:text-paper"}`}
            >
              {option}
            </button>
          ))}
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-xs text-paper/65">
          <input
            type="checkbox"
            checked={drawdown}
            onChange={(event) => setDrawdown(event.target.checked)}
            className="h-4 w-4 accent-amber"
          />
          Drawdown
        </label>
      </div>
      <HistoryChart history={visibleHistory} compact={false} drawdown={drawdown} />
      <div className="mt-2 text-right text-xs text-paper/40">{visibleHistory.length} daily observations</div>
    </div>
  );
}
