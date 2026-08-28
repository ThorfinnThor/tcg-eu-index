const fallbackSiteUrl = "https://tcg-eu-index-web.shuu9599.workers.dev";

export function getSiteUrl() {
  const configured = process.env.NEXT_PUBLIC_SITE_URL ?? fallbackSiteUrl;
  return configured.replace(/\/$/, "");
}
