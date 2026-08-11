import type { Metadata } from "next";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { PortfolioWorkbench } from "@/components/PortfolioWorkbench";
import { getConstituents, getIndexes } from "@/lib/data";
import { utilityPageMetadata } from "@/lib/seo";
import type { IndexCode } from "@/lib/types";

export const metadata: Metadata = utilityPageMetadata(
  "Portfolio benchmark",
  "Compare a trading card collection CSV with European listing-price benchmarks in your browser.",
  "/portfolio"
);

export default async function PortfolioPage() {
  const indexes = await getIndexes();
  const publishedIndexes = indexes.filter((index) => index.status === "published" && index.history.length > 0);
  const constituentEntries = await Promise.all(publishedIndexes.map(async (index) => [index.code, await getConstituents(index.code)] as const));
  const constituentsByCode = Object.fromEntries(constituentEntries) as Record<IndexCode, Awaited<ReturnType<typeof getConstituents>>>;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <Breadcrumbs items={[{ label: "Overview", href: "/" }, { label: "Portfolio benchmark" }]} />
      <div className="border-b border-line pb-6">
        <p className="text-sm text-amber">CSV upload preview</p>
        <h1 className="mt-2 text-3xl font-semibold">Portfolio benchmark</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-paper/65">
          Upload holdings with cm_product_id, variant_key, quantity, and optional cost_basis_eur. Unmatched IDs are reported and never silently dropped.
        </p>
      </div>
      {publishedIndexes.length > 0 ? (
        <PortfolioWorkbench indexes={publishedIndexes} constituentsByCode={constituentsByCode} />
      ) : (
        <section className="mt-6 border-l-2 border-amber bg-amber/[0.06] px-5 py-5" role="status">
          <h2 className="text-lg font-semibold">Portfolio comparison is not available yet</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-paper/65">
            This tool requires published index constituents and prices. It will be enabled after the first real Cardmarket-derived compositions pass the cutover review.
          </p>
        </section>
      )}
    </div>
  );
}
