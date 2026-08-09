import type { MetadataRoute } from "next";
import { getIndexes } from "@/lib/data";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "https://tcg-eu-index.vercel.app";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const indexes = await getIndexes();
  const staticRoutes = ["", "/methodology", "/reports", "/portfolio", "/data-quality"];
  const indexRoutes = indexes.flatMap((index) => [`/index/${index.code}`, `/index/${index.code}/constituents`]);

  return [...staticRoutes, ...indexRoutes].map((route) => ({
    url: `${siteUrl}${route}`,
    lastModified: new Date(),
    changeFrequency: "daily",
    priority: route === "" ? 1 : route.startsWith("/index/") ? 0.8 : 0.6
  }));
}
