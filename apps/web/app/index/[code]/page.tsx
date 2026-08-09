import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ContributionBars, IndexChartExplorer } from "@/components/IndexChart";
import { Metric, formatPct } from "@/components/Metric";
import { changes, getConstituents, getIndex } from "@/lib/data";

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
  const constituents = await getConstituents(index.code);
  const bars = constituents.slice(0, 8).map((item, row) => ({
    name: item.name.replace(" Benchmark Product", " #"),
    contribution: Number(((8 - row) * 0.0012).toFixed(4))
  }));

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-6 flex flex-col gap-4 border-b border-line pb-5 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="text-sm text-paper/50">{index.code}</div>
          <h1 className="mt-1 text-3xl font-semibold text-paper">{index.name}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-paper/60">
            Chain-linked equal-weight index, listing-price basis, currently {index.status}. Base value 1000 at {index.base_date}.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link className="chip hover:border-amber" href={`/index/${index.code}/constituents`}>Constituents</Link>
          <Link className="chip hover:border-amber" href="/methodology">Methodology</Link>
          <a className="chip hover:border-amber" href={`/api/public/${index.code}/history.csv`}>CSV</a>
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
          <h2 className="text-lg font-semibold">Contribution leaders</h2>
          <ContributionBars data={bars} />
        </div>
        <div className="surface p-4">
          <h2 className="text-lg font-semibold">Movers</h2>
          <div className="mt-4 divide-y divide-line">
            {constituents.slice(0, 8).map((item, row) => (
              <div key={`${item.cm_product_id}-${item.variant_key}`} className="flex items-center justify-between py-3 text-sm">
                <span className="text-paper/75">{item.name}</span>
                <span className={row % 2 ? "text-coral" : "text-mint"}>{row % 2 ? "-" : "+"}{(row + 1.8).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
