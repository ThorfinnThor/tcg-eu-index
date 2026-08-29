import type { Metadata } from "next";
import Link from "next/link";
import { IndexChart } from "@/components/IndexChart";
import { Metric, formatPct } from "@/components/Metric";
import { StructuredData } from "@/components/StructuredData";
import { getCollectorPreviewIndex } from "@/lib/collector-data";
import { collectorGameName } from "@/lib/collector-ui";
import { changes, getIndexes, getStatus } from "@/lib/data";
import { assessFreshness, freshnessClass } from "@/lib/freshness";
import { pageMetadata } from "@/lib/seo";
import { getSiteUrl } from "@/lib/site";

export const revalidate = 3600;
export const metadata: Metadata = pageMetadata(
  "overview",
  "European trading card market benchmarks",
  "Track European trading card listing-price indexes, breadth, volatility, and data freshness."
);

export default async function Page() {
  const [indexes, status, collectorPreview] = await Promise.all([
    getIndexes(),
    getStatus(),
    getCollectorPreviewIndex()
  ]);
  const freshness = assessFreshness(status.last_snapshot_date);
  const siteUrl = getSiteUrl();
  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <StructuredData value={[
        {
          "@context": "https://schema.org",
          "@type": "WebSite",
          name: "European TCG Index",
          url: siteUrl,
          description: "EU-first listing-price benchmarks for major trading card games."
        },
        {
          "@context": "https://schema.org",
          "@type": "ItemList",
          name: "European TCG indexes",
          itemListElement: indexes.map((index, position) => ({
            "@type": "ListItem",
            position: position + 1,
            name: index.name,
            url: `${siteUrl}/index/${index.code}`
          }))
        }
      ]} />
      <section className="mb-6 border-b border-line pb-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-sm text-amber">European TCG index development.</p>
            <h1 className="mt-2 text-3xl font-semibold text-paper sm:text-4xl">Market overview</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm text-paper/60">
            <span>Last snapshot: {status.last_snapshot_date ?? "pending"}</span>
            <span className={`chip ${freshnessClass(freshness.level)}`}>{freshness.label}</span>
          </div>
        </div>
        <p className="mt-4 max-w-3xl text-sm leading-6 text-paper/65">
          Official Cardmarket files are archived and checked daily. Provisional index values and compositions are published during the 60-day observation phase; official indexes still require the full history window and human cutover review.
        </p>
      </section>

      {collectorPreview.indexes.length > 0 ? (
        <section className="mb-8">
          <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-sm text-amber">New collector methodology · singles only</p>
              <h2 className="mt-1 text-2xl font-semibold text-paper">Collector preview indexes</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-paper/60">
                Every eligible Cardmarket single-card variant with AVG30 of at least €10. Preview values and monthly compositions are provisional throughout the observation phase.
              </p>
            </div>
            <span className="chip border-amber text-amber">Not official</span>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {collectorPreview.indexes.map((index) => (
              <Link
                key={index.code}
                href={`/collector/${index.code}`}
                className="surface block p-4 transition hover:border-amber"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-xs text-paper/45">{index.code}</div>
                    <h3 className="mt-1 font-semibold text-paper">{index.name}</h3>
                    <div className="mt-2 text-xs text-paper/50">{collectorGameName(index.game_key)}</div>
                  </div>
                  <span className="chip border-amber text-amber">Preview</span>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-4">
                  <Metric label="Latest" value={index.latest_index_value?.toFixed(2) ?? "pending"} />
                  <Metric label="Variants" value={index.constituent_count.toLocaleString("en-GB")} />
                </div>
                <p className="mt-4 border-t border-line pt-3 text-xs leading-5 text-paper/45">
                  Provisional · no target size · AVG30 ≥ €10
                </p>
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        {indexes.map((index) => {
          const visible = ["preview", "published"].includes(index.status) && index.history.length > 0;
          const memberLabel = index.universe === "sealed" ? "products" : "cards";
          const latest = index.history.at(-1);
          const delta = changes(index);
          return (
            <Link key={index.code} href={`/index/${index.code}`} className="surface block p-4 transition hover:border-amber">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-xs text-paper/45">{index.code}</div>
                  <h2 className="mt-1 text-xl font-semibold text-paper">{index.name}</h2>
                  <div className="mt-2 flex gap-2 text-paper/55">
                    <span className="chip">{index.game}</span>
                    <span className="chip">{index.universe}</span>
                  </div>
                </div>
                <span className={`chip ${index.status === "published" ? "border-teal text-teal" : "border-amber text-amber"}`}>
                  {index.status === "preview" ? "Preview index" : index.status}
                </span>
              </div>
              {visible ? (
                <>
                  <div className="mt-5 grid grid-cols-2 gap-4">
                    <Metric label="Latest" value={latest?.index_value.toFixed(2) ?? "pending"} />
                    <Metric label="30d" value={formatPct(delta.d30)} tone={delta.d30 >= 0 ? "up" : "down"} />
                  </div>
                  <div className="mt-4">
                    <IndexChart history={index.history.slice(-90)} compact />
                  </div>
                  <div className="mt-4 flex justify-between text-sm text-paper/55">
                    <span>1d {formatPct(delta.d1)}</span>
                    <span>7d {formatPct(delta.d7)}</span>
                    <span>Breadth {(index.breadth * 100).toFixed(0)}%</span>
                  </div>
                  {index.status === "preview" ? (
                    <p className="mt-4 border-t border-line pt-3 text-xs leading-5 text-amber/85">
                      Provisional values and composition; not the official index or investment advice.
                    </p>
                  ) : null}
                </>
              ) : (
                <div className="mt-6 border-t border-line pt-5">
                  <div className="text-xl font-semibold text-paper">Publication pending</div>
                  <p className="mt-2 text-sm leading-6 text-paper/55">
                    Collecting the observation history required for {index.target_size} real {memberLabel}.
                  </p>
                </div>
              )}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
