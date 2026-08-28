import { readFile } from "node:fs/promises";
import path from "node:path";

function assetPath(relativePath: string) {
  if (relativePath.startsWith("/") || relativePath.split("/").includes("..")) {
    throw new Error(`Invalid asset path: ${relativePath}`);
  }
  return path.join(process.cwd(), "public", relativePath);
}

export async function readAssetText(relativePath: string): Promise<string> {
  return readFile(assetPath(relativePath), "utf8");
}
