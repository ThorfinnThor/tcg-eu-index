import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { CollectorShadowPanel } from "@/components/CollectorShadowPanel";
import { getCollectorDataset } from "@/lib/collector-data";
import type { CollectorIndexCode } from "@/lib/types";

export const dynamic = "force-dynamic";

const collectorCodePattern = /^(?:MTEU|YGEU|OPEU|PKEU|DBSEU|FABEU|DGEU|LCEU|SWUEU|RBEU)COL$/;

export const metadata: Metadata = {
  title: "Collector preview",
  robots: { index: false, follow: false }
};

export default async function CollectorShadowPage(props: {
  params: Promise<{ code: string }>;
  searchParams: Promise<{ date?: string; page?: string }>;
}) {
  if (process.env.COLLECTOR_PREVIEW_UI_ENABLED !== "true") notFound();
  const [params, searchParams] = await Promise.all([props.params, props.searchParams]);
  if (!collectorCodePattern.test(params.code)) notFound();
  const requestedPage = Number.parseInt(searchParams.page ?? "1", 10);
  const dataset = await getCollectorDataset(params.code as CollectorIndexCode, {
    effectiveDate: searchParams.date,
    page: Number.isFinite(requestedPage) ? requestedPage : 1
  });
  if (!dataset) notFound();
  return <CollectorShadowPanel {...dataset} />;
}
