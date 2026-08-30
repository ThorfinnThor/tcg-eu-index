import { env } from "cloudflare:workers";
import type { StoredCardImage } from "./card-image-store";

export async function readCardImage(key: string): Promise<StoredCardImage | null> {
  const object = await env.CARD_IMAGES.get(`card-images/${key}`);
  if (!object) return null;
  return {
    body: await object.arrayBuffer(),
    contentType: object.httpMetadata?.contentType ?? "application/octet-stream",
    etag: object.httpEtag
  };
}
