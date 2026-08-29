import type { Metadata } from "next";
import Link from "next/link";
import { Metric } from "@/components/Metric";
import { StructuredData } from "@/components/StructuredData";
import { getCollectorPreviewIndex } from "@/lib/collector-data";
import { collectorGameName } from "@/lib/collector-ui";
import { pageMetadata } from "@/lib/seo";
import { getSiteUrl } from "@/lib/site";

export const revalidate = 3600;
export const metadata: Metadata = pageMetadata(
  "overview",
  "European collector card indexes",
  "Track preview indexes for European collector card markets using Cardmarket price history."
);

export default async function Page() {
  const collectorPreview = await getCollectorPreviewIndex();
  const siteUrl = getSiteUrl();

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <StructuredData value={[
        {
          "@context": "https://schema.org",
          "@type": "WebSite",
          name: "European TCG Index",
          url: siteUrl,
          description: "European collector card market indexes."
        },
        {
          "@context": "https://schema.org",
          "@type": "ItemList",
          name: "European collector card indexes",
          itemListElement: collectorPreview.indexes.map((index, position) => ({
            "@type": "ListItem",
            position: position + 1,
            name: index.name,
            url: `${siteUrl}/collector/${index.code}`
          }))
        }
      ]} />

      <section className="mb-7 border-b border-line pb-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-sm text-amber">Singles only · preview phase</p>
            <h1 className="mt-2 text-3xl font-semibold text-paper sm:text-4xl">European collector card indexes</h1>
          </div>
          <span className="chip border-amber text-amber">Updated {collectorPreview.generated_for}</span>
        </div>
        <p className="mt-4 max-w-3xl text-sm leading-6 text-paper/65">
          Each index follows every Cardmarket single-card variant whose 30-day average price was at least €10 at the monthly update. The preview started at 1,000; a current value of 1,010 means the basket has gained 1% since its start.
        </p>
        <p className="mt-2 max-w-3xl text-xs leading-5 text-paper/45">
          These values are provisional during the 60-day observation phase. Sealed products and the former fixed-size indexes are not part of this view.
        </p>
      </section>

      <section>
        <div className="mb-4 flex items-end justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold text-paper">Choose a card game</h2>
            <p className="mt-1 text-sm text-paper/55">Open an index to browse and search every included card.</p>
          </div>
          <span className="text-xs text-paper/45">{collectorPreview.indexes.length} indexes</span>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {collectorPreview.indexes.map((index) => (
            <Link
              key={index.code}
              href={`/collector/${index.code}`}
              className="surface block p-5 transition hover:border-amber"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs text-paper/45">{collectorGameName(index.game_key)}</div>
                  <h3 className="mt-1 text-lg font-semibold text-paper">{index.name}</h3>
                </div>
                <span className="chip border-amber text-amber">Preview</span>
              </div>
              <div className="mt-5 grid grid-cols-2 gap-4">
                <Metric
                  label={`Index value · ${index.latest_value_date ?? "pending"}`}
                  value={index.latest_index_value?.toFixed(2) ?? "pending"}
                />
                <Metric label="Cards tracked" value={index.constituent_count.toLocaleString("en-GB")} />
              </div>
              <p className="mt-4 border-t border-line pt-3 text-xs leading-5 text-paper/45">
                Singles priced from €10 · basket updated monthly
              </p>
            </Link>
          ))}
        </div>

        {collectorPreview.indexes.length === 0 ? (
          <div className="surface p-6 text-sm text-paper/55">Collector index data is being prepared.</div>
        ) : null}
      </section>
    </div>
  );
}
