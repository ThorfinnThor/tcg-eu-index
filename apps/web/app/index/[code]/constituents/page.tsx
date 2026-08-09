import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ConstituentsTable } from "@/components/ConstituentsTable";
import { latestCompositionDate } from "@/lib/constituents";
import { getConstituents, getIndex } from "@/lib/data";

export const revalidate = 3600;
export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: { code: string } }): Promise<Metadata> {
  const index = await getIndex(params.code);
  if (!index) return { title: "Constituents not found" };
  return {
    title: `${index.name} constituents`,
    description: `Search and replay the historical constituent composition of ${index.name}.`,
    alternates: { canonical: `/index/${index.code}/constituents` }
  };
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
  const constituents = await getConstituents(params.code);
  const maxDate = latestCompositionDate(constituents, index.history.at(-1)?.value_date ?? index.base_date);
  const requestedAsOf = searchParams.asOf;
  const asOf = requestedAsOf && requestedAsOf >= index.base_date && requestedAsOf <= maxDate ? requestedAsOf : maxDate;
  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-6 border-b border-line pb-5">
        <div className="text-sm text-paper/50">{index.code}</div>
        <h1 className="mt-1 text-3xl font-semibold">Constituents</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-paper/60">
          Replay the active composition at any available date and search the resulting membership snapshot.
        </p>
      </div>
      <ConstituentsTable
        constituents={constituents}
        initialAsOf={asOf}
        initialSearch={searchParams.q ?? ""}
        initialIncludeInactive={searchParams.inactive === "1"}
        minDate={index.base_date}
        maxDate={maxDate}
      />
    </div>
  );
}
