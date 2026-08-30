import { readCardImage } from "@card-image-store";

export const runtime = "edge";

export async function GET(
  _request: Request,
  context: { params: Promise<{ key: string[] }> }
) {
  const { key } = await context.params;
  if (!key.length || key.some((part) => !/^[A-Za-z0-9._-]+$/.test(part))) {
    return new Response("Invalid image key", { status: 400 });
  }
  const image = await readCardImage(key.join("/"));
  if (!image) return new Response("Image not found", { status: 404 });
  return new Response(image.body, {
    headers: {
      "Content-Type": image.contentType,
      "Cache-Control": "public, max-age=86400, immutable",
      ETag: image.etag,
      "X-Content-Type-Options": "nosniff"
    }
  });
}
