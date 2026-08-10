import type { BreadcrumbItem } from "@/components/Breadcrumbs";

export type JsonLdValue = Record<string, unknown> | Array<Record<string, unknown>>;

export function breadcrumbStructuredData(siteUrl: string, items: BreadcrumbItem[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.label,
      ...(item.href ? { item: new URL(item.href, siteUrl).toString() } : {})
    }))
  };
}

export function indexDatasetStructuredData({
  siteUrl,
  code,
  name,
  description,
  startDate,
  endDate
}: {
  siteUrl: string;
  code: string;
  name: string;
  description: string;
  startDate: string;
  endDate: string | null;
}) {
  return {
    "@context": "https://schema.org",
    "@type": "Dataset",
    name,
    alternateName: code,
    description,
    url: new URL(`/index/${code}`, siteUrl).toString(),
    temporalCoverage: `${startDate}/${endDate ?? ".."}`,
    creator: { "@type": "Organization", name: "European TCG Index" },
    measurementTechnique: "Liquidity-screened, equal-weighted, chain-linked listing-price index",
    variableMeasured: ["Index value", "Daily return", "Breadth", "Listing-price volatility"],
    distribution: {
      "@type": "DataDownload",
      encodingFormat: "text/csv",
      contentUrl: new URL(`/api/public/${code}/history.csv`, siteUrl).toString()
    }
  };
}
