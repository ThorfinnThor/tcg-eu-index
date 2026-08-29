import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { CollectorShadowPanel } from "@/components/CollectorShadowPanel";
import { getCollectorDataset } from "@/lib/collector-data";
import type { CollectorIndexCode } from "@/lib/types";

export const dynamic = "force-dynamic";

const collectorCodePattern = /^(?:MTEU|YGEU|OPEU|PKEU|DBSEU|FABEU|DGEU|LCEU|SWUEU|RBEU)(?:COL|SCOL)$/;

export const metadata: Metadata = {
  title: "Collector shadow",
  robots: { index: false, follow: false }
};

export default async function CollectorShadowPage(props: { params: Promise<{ code: string }> }) {
  if (process.env.COLLECTOR_SHADOW_UI_ENABLED !== "true") notFound();
  const params = await props.params;
  if (!collectorCodePattern.test(params.code)) notFound();
  const dataset = await getCollectorDataset(params.code as CollectorIndexCode);
  if (!dataset) notFound();
  return <CollectorShadowPanel {...dataset} />;
}
