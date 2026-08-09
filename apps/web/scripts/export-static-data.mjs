import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const dataRoot = path.join(root, "public", "data");
const sourceDataRoot = path.join(root, "source-data");
const sourceDataPath = path.join(sourceDataRoot, "indexes.json");

async function readSourceJson(indexCode, fileName) {
  return JSON.parse(await readFile(path.join(sourceDataRoot, "indexes", indexCode, fileName), "utf8"));
}

async function writeJson(relativePath, payload) {
  const destination = path.join(dataRoot, relativePath);
  await mkdir(path.dirname(destination), { recursive: true });
  const body = `${JSON.stringify(payload, null, 2)}\n`;
  await writeFile(destination, body);
  return {
    path: `data/${relativePath}`,
    checksum: createHash("sha256").update(body).digest("hex"),
    bytes: Buffer.byteLength(body)
  };
}

const generatedAt = new Date().toISOString();
const fileStats = [];
const sourceData = JSON.parse(await readFile(sourceDataPath, "utf8"));
const indexes = await Promise.all(
  sourceData.indexes.map(async (index) => ({
    ...index,
    history: await readSourceJson(index.code, "history.json"),
    constituents: await readSourceJson(index.code, "constituents.json")
  }))
);

fileStats.push(
  await writeJson(
    "search/indexes.json",
    indexes.map(({ code, slug, name, game, universe, status, target_size, breadth, history }) => ({
      id: code,
      slug,
      name,
      score: history.at(-1)?.index_value ?? 1000,
      category: universe,
      filterValues: { game, universe, status, target_size, breadth }
    }))
  )
);

const status = {
  last_snapshot_date: indexes
    .map((index) => index.history.at(-1)?.value_date)
    .filter(Boolean)
    .sort()
    .at(-1),
  last_calc_date: indexes
    .map((index) => index.history.at(-1)?.value_date)
    .filter(Boolean)
    .sort()
    .at(-1),
  gap_count: 0,
  indexes: indexes.map((index) => ({
    code: index.code,
    freshness: index.history.at(-1)?.value_date ?? null,
    status: index.status
  }))
};

fileStats.push(await writeJson("status/latest.json", status));

for (const index of indexes) {
  const summary = { ...index };
  delete summary.history;
  delete summary.constituents;
  fileStats.push(await writeJson(`indexes/${index.code}/summary.json`, summary));
  fileStats.push(await writeJson(`indexes/${index.code}/history.json`, index.history));
  fileStats.push(await writeJson(`indexes/${index.code}/constituents.json`, index.constituents));
}

const manifestBody = {
  datasetVersion: sourceData.datasetVersion,
  generatedAt,
  schemaVersion: sourceData.schemaVersion,
  sourceVersions: {
    methodology: "1.0.0",
    source: sourceData.source
  },
  fileChecksums: Object.fromEntries(fileStats.map((file) => [file.path, file.checksum])),
  files: fileStats
};

await writeJson("manifest.json", manifestBody);
console.log(`exported ${fileStats.length + 1} static data files`);
