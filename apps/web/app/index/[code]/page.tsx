import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { IndexChartExplorer } from "@/components/IndexChart";
import { Metric, formatPct } from "@/components/Metric";
import { changes, getIndex } from "@/lib/data";
import { calculateIndexAnalytics } from "@/lib/index-analytics";

export const revalidate = 3600;
export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: { code: string } }): Promise<Metadata> {
  const index = await getIndex(params.code);
  if (!index) return { title: "Index not found" };
  return {
    title: index.name,
    description: `${index.name} tracks ${index.game} ${index.universe} listing prices in Europe with transparent methodology and daily history.`,
    alternates: { canonical: `/index/${index.code}` }
  };
}

export default async function IndexPage({ params }: { params: { code: string } }) {
  const index = await getIndex(params.code);
  if (!index) notFound();
  const delta = changes(index);
  const latest = index.history.at(-1);
  const analytics = calculateIndexAnalytics(index.history);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-6 flex flex-col gap-4 border-b border-line pb-5 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="text-sm text-paper/50">{index.code}</div>
          <h1 className="mt-1 text-3xl font-semibold text-paper">{index.name}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-paper/60">
            Chain-linked equal-weight index on a listing-price basis, currently {index.status}. Formal MVP inception: {index.base_date}.
          </p>
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-paper/50">
            <span className="chip">Repo-managed MVP data</span>
            <span className="chip">Latest calculation {latest?.value_date ?? "pending"}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link className="chip hover:border-amber" href={`/index/${index.code}/constituents`}>Constituents</Link>
          <Link className="chip hover:border-amber" href="/methodology">Methodology</Link>
          <a className="chip hover:border-amber" href={`/api/public/${index.code}/history.csv`} download>CSV</a>
        </div>
      </div>

      <section className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="surface p-4">
          <IndexChartExplorer history={index.history} />
        </div>
        <aside className="surface p-4">
          <div className="grid grid-cols-2 gap-5">
            <Metric label="Latest" value={latest?.index_value.toFixed(2) ?? "pending"} />
            <Metric label="1d" value={formatPct(delta.d1)} tone={delta.d1 >= 0 ? "up" : "down"} />
            <Metric label="7d" value={formatPct(delta.d7)} tone={delta.d7 >= 0 ? "up" : "down"} />
            <Metric label="30d" value={formatPct(delta.d30)} tone={delta.d30 >= 0 ? "up" : "down"} />
            <Metric label="Breadth" value={`${(index.breadth * 100).toFixed(0)}%`} />
            <Metric label="Vol 30d" value={`${(index.volatility_30d * 100).toFixed(0)}%`} />
          </div>
        </aside>
      </section>

      <section className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="surface p-4">
          <h2 className="text-lg font-semibold">Available-history analytics</h2>
          <p className="mt-2 text-xs leading-5 text-paper/45">
            Calculated from {analytics.startDate} through {analytics.endDate}; these figures describe the available MVP history, not executed transactions.
          </p>
          <div className="mt-5 grid grid-cols-2 gap-5 sm:grid-cols-3">
            <Metric label="Period return" value={formatPct(analytics.periodReturn)} tone={analytics.periodReturn >= 0 ? "up" : "down"} />
            <Metric label="Max drawdown" value={formatPct(analytics.maxDrawdown)} tone="down" />
            <Metric label="Positive days" value={`${(analytics.positiveDayRatio * 100).toFixed(0)}%`} />
            <Metric label="Best day" value={formatPct(analytics.bestDay?.daily_return ?? 0)} tone="up" />
            <Metric label="Worst day" value={formatPct(analytics.worstDay?.daily_return ?? 0)} tone="down" />
            <Metric label="Volatility 30d" value={`${(analytics.annualizedVolatility30d * 100).toFixed(1)}%`} />
          </div>
        </div>
        <div className="surface p-4">
          <h2 className="text-lg font-semibold">Calculation coverage</h2>
          <div className="mt-4 divide-y divide-line text-sm">
            <div className="flex items-center justify-between py-3">
              <span className="text-paper/60">Daily observations</span>
              <span>{analytics.observationCount}</span>
            </div>
            <div className="flex items-center justify-between py-3">
              <span className="text-paper/60">Days with caps</span>
              <span>{analytics.cappedDays}</span>
            </div>
            <div className="flex items-center justify-between py-3">
              <span className="text-paper/60">Days with carried values</span>
              <span>{analytics.carriedForwardDays}</span>
            </div>
          </div>
          <div className="mt-4 border-t border-line pt-4">
            <h3 className="text-sm font-semibold text-paper">Per-card movers and contributions</h3>
            <p className="mt-2 text-xs leading-5 text-paper/50">
              Unavailable in the JSON-only MVP because the repository does not yet contain per-constituent daily return series. No synthetic rankings are displayed.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
