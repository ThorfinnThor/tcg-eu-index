import type { MetadataRoute } from "next";
import { getStatus } from "@/lib/data";
import { getPageDefinitions, isIndexable } from "@/lib/seo";
import { getSiteUrl } from "@/lib/site";

const siteUrl = getSiteUrl();

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const status = await getStatus();
  const lastModified = status.last_calc_date ? new Date(`${status.last_calc_date}T00:00:00Z`) : undefined;
  return getPageDefinitions().filter(isIndexable).map((definition) => ({
    url: `${siteUrl}${definition.canonical === "/" ? "" : definition.canonical}`,
    lastModified,
    changeFrequency: "daily",
    priority: definition.id === "overview" ? 1 : definition.template === "index-detail" ? 0.8 : 0.6
  }));
}
