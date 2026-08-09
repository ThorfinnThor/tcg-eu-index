import type { MetadataRoute } from "next";
import { getIndexes, getReports } from "@/lib/data";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "https://tcg-eu-index.vercel.app";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [indexes, reports] = await Promise.all([getIndexes(), getReports()]);
  const staticRoutes = ["", "/methodology", "/reports", "/portfolio", "/data-quality"];
  const indexRoutes = indexes.flatMap((index) => [`/index/${index.code}`, `/index/${index.code}/constituents`]);
  const reportRoutes = reports.reports.filter((report) => report.status === "published").map((report) => `/reports/${report.week}`);

  return [...staticRoutes, ...indexRoutes, ...reportRoutes].map((route) => ({
    url: `${siteUrl}${route}`,
    lastModified: new Date(),
    changeFrequency: "daily",
    priority: route === "" ? 1 : route.startsWith("/index/") ? 0.8 : 0.6
  }));
}
