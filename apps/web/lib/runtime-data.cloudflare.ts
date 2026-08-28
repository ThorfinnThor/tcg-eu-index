import { env } from "cloudflare:workers";

function assetUrl(relativePath: string) {
  if (relativePath.startsWith("/") || relativePath.split("/").includes("..")) {
    throw new Error(`Invalid asset path: ${relativePath}`);
  }
  return new URL(relativePath, "https://assets.local/");
}

export async function readAssetText(relativePath: string): Promise<string> {
  const response = await env.ASSETS.fetch(assetUrl(relativePath));
  if (!response.ok) {
    throw new Error(`Asset ${relativePath} returned ${response.status}`);
  }
  return response.text();
}
