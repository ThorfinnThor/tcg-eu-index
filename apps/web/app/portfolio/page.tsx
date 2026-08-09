import type { Metadata } from "next";
import { PortfolioWorkbench } from "@/components/PortfolioWorkbench";
import { getConstituents, getIndexes } from "@/lib/data";
import type { IndexCode } from "@/lib/types";

export const metadata: Metadata = {
  title: "Portfolio benchmark",
  description: "Compare a trading card collection CSV with European One Piece and Pokemon listing-price benchmarks in your browser."
};

export default async function PortfolioPage() {
  const indexes = await getIndexes();
  const constituentEntries = await Promise.all(indexes.map(async (index) => [index.code, await getConstituents(index.code)] as const));
  const constituentsByCode = Object.fromEntries(constituentEntries) as Record<IndexCode, Awaited<ReturnType<typeof getConstituents>>>;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="border-b border-line pb-6">
        <p className="text-sm text-amber">CSV upload preview</p>
        <h1 className="mt-2 text-3xl font-semibold">Portfolio benchmark</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-paper/65">
          Upload holdings with cm_product_id, variant_key, quantity, and optional cost_basis_eur. Unmatched IDs are reported and never silently dropped.
        </p>
      </div>
      <PortfolioWorkbench indexes={indexes} constituentsByCode={constituentsByCode} />
    </div>
  );
}
