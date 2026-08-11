import type { Metadata } from "next";
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
    `Search and replay the historical constituent composition of ${index.name}.`,
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
      {rebalances.data_state === "validation" ? (
        <div className="mb-7 border-l-2 border-amber bg-amber/[0.06] px-4 py-4" role="status">
          <div className="text-sm font-medium text-amber">Validation composition</div>
          <p className="mt-1 max-w-4xl text-sm leading-6 text-paper/60">
            These are synthetic benchmark rows used to validate the interface and calculation workflow. They are not real Cardmarket index members. The production composition will replace them only after the private archive meets the 60-day selection window and passes the cutover review.
          </p>
        </div>
      ) : null}
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
