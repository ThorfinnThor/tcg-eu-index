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

async function readSourceFile(relativePath) {
  return JSON.parse(await readFile(path.join(sourceDataRoot, relativePath), "utf8"));
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

function activeAsOf(constituents, asOf) {
  return constituents.filter((item) => item.member_since <= asOf && (!item.removed_at || item.removed_at > asOf));
}

function deriveRebalances(index, constituents, methodologyVersion) {
  const dates = [...new Set(constituents.flatMap((item) => [item.member_since, item.removed_at].filter(Boolean)))].sort();
  const generatedFor = dates.at(-1) ?? index.base_date;
  return {
    schema_version: 1,
    index_code: index.code,
    data_state: index.history_start_kind === "published" ? "published" : "validation",
    cadence: "monthly",
    generated_for: generatedFor,
    rebalances: dates.map((effectiveDate, position) => {
      const additions = constituents.filter((item) => item.member_since === effectiveDate);
      const removals = constituents.filter((item) => item.removed_at === effectiveDate);
      const active = activeAsOf(constituents, effectiveDate);
      return {
        effective_date: effectiveDate,
        methodology_version: methodologyVersion,
        selection_snapshot_sha256: null,
        eligible_count: null,
        active_count: active.length,
        retained_count: Math.max(active.length - additions.length, 0),
        changes: [
          ...additions.map((item) => ({
            cm_product_id: item.cm_product_id,
            variant_key: item.variant_key,
            action: "added",
            reason: item.entry_reason ?? (position === 0 ? "Initial composition" : "Entered the selection")
          })),
          ...removals.map((item) => ({
            cm_product_id: item.cm_product_id,
            variant_key: item.variant_key,
            action: "removed",
            reason: item.removal_reason ?? "Left the selection"
          }))
        ]
      };
    })
  };
}

const generatedAt = new Date().toISOString();
const fileStats = [];
const sourceData = JSON.parse(await readFile(sourceDataPath, "utf8"));
const dataQuality = await readSourceFile("data-quality.json");
const reports = await readSourceFile("reports/index.json");
const indexes = await Promise.all(
  sourceData.indexes.map(async (index) => {
    const published = index.status === "published" && index.history_start_kind === "published";
    return {
      ...index,
      breadth: published ? index.breadth : 0,
      volatility_30d: published ? index.volatility_30d : 0,
      history: published ? await readSourceJson(index.code, "history.json") : [],
      constituents: published ? await readSourceJson(index.code, "constituents.json") : []
    };
  })
);

fileStats.push(
  await writeJson(
    "search/indexes.json",
    indexes.map(({ code, slug, name, game, universe, status, target_size, breadth, history }) => ({
      id: code,
      slug,
      name,
      score: status === "published" ? history.at(-1)?.index_value ?? null : null,
      category: universe,
      filterValues: { game, universe, status, target_size, breadth }
    }))
  )
);

const status = {
  dataset_version: sourceData.datasetVersion,
  generated_at: generatedAt,
  source: sourceData.source,
  last_snapshot_date: indexes
    .map((index) => index.history.at(-1)?.value_date)
    .filter(Boolean)
    .sort()
    .at(-1) ?? null,
  last_calc_date: indexes
    .map((index) => index.history.at(-1)?.value_date)
    .filter(Boolean)
    .sort()
    .at(-1) ?? null,
  gap_count: dataQuality.gaps.length,
  indexes: indexes.map((index) => ({
    code: index.code,
    freshness: index.history.at(-1)?.value_date ?? null,
    status: index.status
  }))
};

fileStats.push(await writeJson("status/latest.json", status));
fileStats.push(await writeJson("data-quality/latest.json", dataQuality));
fileStats.push(await writeJson("reports/index.json", {
  ...reports,
  reports: reports.reports.filter((report) => report.status === "published")
}));

for (const index of indexes) {
  const summary = { ...index };
  delete summary.history;
  delete summary.constituents;
  fileStats.push(await writeJson(`indexes/${index.code}/summary.json`, summary));
  fileStats.push(await writeJson(`indexes/${index.code}/history.json`, index.history));
  fileStats.push(await writeJson(`indexes/${index.code}/constituents.json`, index.constituents));
  fileStats.push(await writeJson(
    `indexes/${index.code}/rebalances.json`,
    deriveRebalances(index, index.constituents, sourceData.methodologyVersion)
  ));
}

const manifestBody = {
  datasetVersion: sourceData.datasetVersion,
  generatedAt,
  schemaVersion: sourceData.schemaVersion,
  sourceVersions: {
    methodology: sourceData.methodologyVersion,
    source: sourceData.source
  },
  fileChecksums: Object.fromEntries(fileStats.map((file) => [file.path, file.checksum])),
  files: fileStats
};

await writeJson("manifest.json", manifestBody);
console.log(`exported ${fileStats.length + 1} static data files`);
