import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { ConstituentsTable } from "@/components/ConstituentsTable";
import { latestCompositionDate } from "@/lib/constituents";
import { getConstituents, getIndex, getRebalanceHistory } from "@/lib/data";
import type { IndexCode } from "@/lib/types";
import { utilityPageMetadata } from "@/lib/seo";

export const revalidate = 3600;
export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: { code: string } }): Promise<Metadata> {
  const index = await getIndex(params.code);
  if (!index) return { title: "Constituents not found" };
  return utilityPageMetadata(
    `${index.name} constituents`,
    index.status === "published"
      ? `Search and replay the historical constituent composition of ${index.name}.`
      : `${index.name} constituents will be published after the Cardmarket archive and cutover review are complete.`,
    `/index/${index.code}/constituents`
  );
}

export default async function ConstituentsPage({
  params,
  searchParams
}: {
  params: { code: string };
  searchParams: { asOf?: string; q?: string; inactive?: string };
}) {
  const index = await getIndex(params.code);
  if (!index) notFound();
  if (index.status !== "published") {
    return (
      <div className="mx-auto max-w-5xl px-4 py-8">
        <Breadcrumbs items={[
          { label: "Overview", href: "/" },
          { label: index.name, href: `/index/${index.code}` },
          { label: "Constituents" }
        ]} />
        <div className="border-b border-line pb-5">
          <div className="text-sm text-paper/50">{index.code}</div>
          <h1 className="mt-1 text-3xl font-semibold">Constituents</h1>
        </div>
        <section className="mt-6 border-l-2 border-amber bg-amber/[0.06] px-5 py-5" role="status">
          <h2 className="text-lg font-semibold text-paper">No cards published yet</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-paper/65">
            Real Cardmarket snapshots are currently being collected. The first constituent list will appear only after the required 60-day observation window, all selection checks, and the human cutover review have passed.
          </p>
          <p className="mt-3 text-sm text-paper/50">
            Target composition: {index.target_size} cards. Synthetic development products are not public index members.
          </p>
          <Link href="/data-quality" className="mt-4 inline-block text-sm font-semibold text-amber hover:text-paper">
            View data readiness
          </Link>
        </section>
      </div>
    );
  }
  const [constituents, rebalances] = await Promise.all([
    getConstituents(params.code),
    getRebalanceHistory(params.code as IndexCode)
  ]);
  const maxDate = latestCompositionDate(constituents, index.history.at(-1)?.value_date ?? index.base_date);
  const requestedAsOf = searchParams.asOf;
  const asOf = requestedAsOf && requestedAsOf >= index.base_date && requestedAsOf <= maxDate ? requestedAsOf : maxDate;
  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <Breadcrumbs items={[
        { label: "Overview", href: "/" },
        { label: index.name, href: `/index/${index.code}` },
        { label: "Constituents" }
      ]} />
      <div className="mb-6 border-b border-line pb-5">
        <div className="text-sm text-paper/50">{index.code}</div>
        <h1 className="mt-1 text-3xl font-semibold">Constituents</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-paper/60">
          Inspect every available composition, compare two snapshots, and audit additions and removals by week or month.
        </p>
      </div>
      <ConstituentsTable
        constituents={constituents}
        rebalances={rebalances}
        initialAsOf={asOf}
        initialSearch={searchParams.q ?? ""}
        initialIncludeInactive={searchParams.inactive === "1"}
        minDate={index.base_date}
        maxDate={maxDate}
        targetSize={index.target_size}
      />
    </div>
  );
}
