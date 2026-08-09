"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import type { DailyIndexValue } from "@/lib/types";

export function IndexChart({ history, compact = false }: { history: DailyIndexValue[]; compact?: boolean }) {
  const data = history.map((row) => ({
    date: row.value_date.slice(5),
    value: Number(row.index_value.toFixed(2)),
    drawdown: Number(((row.index_value / Math.max(...history.map((item) => item.index_value))) - 1).toFixed(4))
  }));
  return (
    <div className={compact ? "h-28" : "h-80"}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ left: 0, right: 8, top: 10, bottom: 0 }}>
          <defs>
            <linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#e7b75f" stopOpacity={0.45} />
              <stop offset="95%" stopColor="#e7b75f" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#34342e" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "#a7a195", fontSize: 12 }} tickLine={false} axisLine={false} />
          <YAxis tick={{ fill: "#a7a195", fontSize: 12 }} tickLine={false} axisLine={false} width={48} />
          <Tooltip
            contentStyle={{ background: "#191916", border: "1px solid #34342e", borderRadius: 8 }}
            labelStyle={{ color: "#f4efe4" }}
          />
          <Area type="monotone" dataKey="value" stroke="#e7b75f" strokeWidth={2} fill="url(#chartFill)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ContributionBars({ data }: { data: { name: string; contribution: number }[] }) {
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 20, right: 16, top: 8, bottom: 8 }}>
          <CartesianGrid stroke="#34342e" horizontal={false} />
          <XAxis type="number" tick={{ fill: "#a7a195", fontSize: 12 }} axisLine={false} tickLine={false} />
          <YAxis type="category" dataKey="name" tick={{ fill: "#a7a195", fontSize: 12 }} axisLine={false} tickLine={false} width={120} />
          <Tooltip contentStyle={{ background: "#191916", border: "1px solid #34342e", borderRadius: 8 }} />
          <Bar dataKey="contribution" fill="#4db7ad" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
