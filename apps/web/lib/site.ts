const fallbackSiteUrl = "https://tcg-eu-index.vercel.app";

export function getSiteUrl() {
  const configured = process.env.NEXT_PUBLIC_SITE_URL ?? fallbackSiteUrl;
  return configured.replace(/\/$/, "");
}
