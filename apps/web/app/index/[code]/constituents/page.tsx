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

export async function generateMetadata(props: { params: Promise<{ code: string }> }): Promise<Metadata> {
  const params = await props.params;
  const index = await getIndex(params.code);
  if (!index) return { title: "Constituents not found" };
  return utilityPageMetadata(
    `${index.name} constituents`,
    ["preview", "published"].includes(index.status)
      ? `Search and replay the historical constituent composition of ${index.name}.`
      : `${index.name} constituents will be published after the Cardmarket archive and cutover review are complete.`,
    `/index/${index.code}/constituents`
  );
}

type ConstituentsPageProps = {
  params: Promise<{ code: string }>;
  searchParams: Promise<{ asOf?: string | string[]; q?: string | string[]; inactive?: string | string[] }>;
};

export default async function ConstituentsPage(props: ConstituentsPageProps) {
  const [params, searchParams] = await Promise.all([props.params, props.searchParams]);
  const index = await getIndex(params.code);
  if (!index) notFound();
  if (!["preview", "published"].includes(index.status)) {
    const memberLabel = index.universe === "sealed" ? "products" : "cards";
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
          <h2 className="text-lg font-semibold text-paper">No {memberLabel} published yet</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-paper/65">
            Real Cardmarket snapshots are currently being collected. The first constituent list will appear only after the required 60-day observation window, all selection checks, and the human cutover review have passed.
          </p>
          <p className="mt-3 text-sm text-paper/50">
            Target composition: {index.target_size} {memberLabel}. Synthetic development products are not public index members.
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
  const requestedAsOf = typeof searchParams.asOf === "string" ? searchParams.asOf : null;
  const initialAsOf = requestedAsOf && requestedAsOf >= index.base_date && requestedAsOf <= maxDate
    ? requestedAsOf
    : maxDate;
  const initialSearch = typeof searchParams.q === "string" ? searchParams.q : "";
  const initialIncludeInactive = searchParams.inactive === "1";
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
      {index.status === "preview" ? (
        <section className="mb-6 border-l-2 border-amber bg-amber/[0.07] px-5 py-4" role="status">
          <h2 className="text-sm font-semibold text-amber">Daily preview composition</h2>
          <p className="mt-2 max-w-4xl text-sm leading-6 text-paper/70">
            These are real Cardmarket-derived provisional members and reference prices. The selection is recalculated daily from the available history and may change materially before the official 60-day cutover.
          </p>
        </section>
      ) : null}
      <ConstituentsTable
        constituents={constituents}
        rebalances={rebalances}
        initialAsOf={initialAsOf}
        initialSearch={initialSearch}
        initialIncludeInactive={initialIncludeInactive}
        minDate={index.base_date}
        maxDate={maxDate}
        targetSize={index.target_size}
      />
    </div>
  );
}
