import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const dataRoot = path.join(root, "public", "data");
const sourceDataPath = path.join(root, "source-data", "indexes.json");

const dates = Array.from({ length: 120 }, (_, index) => {
  const date = new Date(Date.UTC(2026, 3, 1 + index));
  return date.toISOString().slice(0, 10);
});

function curve(seed) {
  let value = 1000;
  return dates.map((day, index) => {
    const daily = Math.sin((index + seed) / 8) * 0.006 + Math.cos((index + seed) / 19) * 0.003;
    value *= 1 + daily;
    return {
      value_date: day,
      index_value: Number(value.toFixed(6)),
      daily_return: Number(daily.toFixed(8)),
      n_constituents_active: seed === 3 ? 25 : seed === 2 ? 250 : 100,
      n_capped: index % 41 === 0 ? 1 : 0,
      n_carried_forward: index % 23 === 0 ? 2 : 0,
      calc_version: "1.0.0"
    };
  });
}

const sourceData = JSON.parse(await readFile(sourceDataPath, "utf8"));
const indexes = sourceData.indexes.map(({ seed, ...index }) => ({
  ...index,
  history: curve(seed)
}));

function constituents(index) {
  return Array.from({ length: Math.min(index.target_size, 40) }, (_, row) => ({
    cm_product_id: 750000 + row,
    variant_key: row % 7 === 0 ? "foil" : "nonfoil",
    name: `${index.game} Benchmark Product ${row + 1}`,
    set: row % 2 === 0 ? "Launch Set" : "Current Set",
    member_since: row < 10 ? "2026-07-20" : "2026-08-01",
    action: row < 10 ? "retained" : "added",
    liquidity_score: Number((0.91 - row * 0.006).toFixed(3)),
    ref_price: Number((2 + row * 1.35).toFixed(2))
  }));
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
  fileStats.push(await writeJson(`indexes/${index.code}/summary.json`, summary));
  fileStats.push(await writeJson(`indexes/${index.code}/history.json`, index.history));
  fileStats.push(await writeJson(`indexes/${index.code}/constituents.json`, constituents(index)));
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
