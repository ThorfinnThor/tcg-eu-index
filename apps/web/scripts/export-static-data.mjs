import { createHash } from "node:crypto";
import { copyFile, cp, mkdir, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const dataRoot = path.join(root, "public", "data");
const sourceDataRoot = path.join(root, "source-data");
const sourceDataPath = path.join(sourceDataRoot, "indexes.json");
const methodologySource = path.join(root, "..", "..", "docs", "methodology", "v1.4.0.md");
const methodologyDestination = path.join(root, "public", "methodology", "v1.4.0.md");
const collectorSource = path.join(sourceDataRoot, "collector");
const collectorDestination = path.join(dataRoot, "collector");

async function readSourceJson(indexCode, fileName) {
  return JSON.parse(await readFile(path.join(sourceDataRoot, "indexes", indexCode, fileName), "utf8"));
}

async function readSourceFile(relativePath) {
  return JSON.parse(await readFile(path.join(sourceDataRoot, relativePath), "utf8"));
}

async function readOptionalSourceJson(indexCode, fileName, fallback) {
  try {
    return await readSourceJson(indexCode, fileName);
  } catch {
    return fallback;
  }
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

async function collectCopiedJsonFiles(directory, relativeRoot) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const absolutePath = path.join(directory, entry.name);
    const relativePath = path.join(relativeRoot, entry.name);
    if (entry.isDirectory()) {
      files.push(...await collectCopiedJsonFiles(absolutePath, relativePath));
    } else if (entry.isFile() && entry.name.endsWith(".json")) {
      const body = await readFile(absolutePath);
      files.push({
        path: `data/${relativePath.split(path.sep).join("/")}`,
        checksum: createHash("sha256").update(body).digest("hex"),
        bytes: body.byteLength
      });
    }
  }
  return files;
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
    data_state: index.history_start_kind,
    cadence: index.history_start_kind === "preview" ? "daily_preview" : "monthly",
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
await rm(collectorDestination, { recursive: true, force: true });
const collectorAvailable = await stat(collectorSource)
  .then((value) => value.isDirectory())
  .catch((error) => {
    if (error?.code === "ENOENT") return false;
    throw error;
  });
if (collectorAvailable) {
  await cp(collectorSource, collectorDestination, { recursive: true });
  fileStats.push(...await collectCopiedJsonFiles(collectorDestination, "collector"));
}
await mkdir(path.dirname(methodologyDestination), { recursive: true });
await copyFile(methodologySource, methodologyDestination);
const sourceData = JSON.parse(await readFile(sourceDataPath, "utf8"));
const dataQuality = await readSourceFile("data-quality.json");
const readiness = await readSourceFile("readiness.json");
const archiveHealth = await readSourceFile("archive-health.json");
const reports = await readSourceFile("reports/index.json");
const publishedReports = reports.reports.filter((report) => report.status === "published");
const indexes = await Promise.all(
  sourceData.indexes.map(async (index) => {
    const visible = ["preview", "published"].includes(index.status)
      && index.status === index.history_start_kind;
    let rebalances;
    try {
      rebalances = await readSourceJson(index.code, "rebalances.json");
    } catch {
      rebalances = null;
    }
    return {
      ...index,
      breadth: visible ? index.breadth : 0,
      volatility_30d: visible ? index.volatility_30d : 0,
      history: visible ? await readSourceJson(index.code, "history.json") : [],
      constituents: visible ? await readSourceJson(index.code, "constituents.json") : [],
      previewHistory: await readOptionalSourceJson(index.code, "preview-history.json", []),
      previewConstituents: await readOptionalSourceJson(index.code, "preview-constituents.json", []),
      previewRebalances: await readOptionalSourceJson(index.code, "preview-rebalances.json", null),
      rebalances
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
      score: ["preview", "published"].includes(status) ? history.at(-1)?.index_value ?? null : null,
      category: universe,
      filterValues: { game, universe, status, target_size, breadth }
    }))
  )
);

const status = {
  dataset_version: sourceData.datasetVersion,
  generated_at: generatedAt,
  source: sourceData.source,
  last_snapshot_date: readiness.generatedFor ?? indexes
    .map((index) => index.history.at(-1)?.value_date)
    .filter(Boolean)
    .sort()
    .at(-1) ?? null,
  last_calc_date: readiness.generatedFor ?? indexes
    .map((index) => index.history.at(-1)?.value_date)
    .filter(Boolean)
    .sort()
    .at(-1) ?? null,
  gap_count: archiveHealth.gapCount ?? dataQuality.gaps.length,
  indexes: indexes.map((index) => ({
    code: index.code,
    freshness: index.history.at(-1)?.value_date ?? null,
    status: index.status
  }))
};

fileStats.push(await writeJson("status/latest.json", status));
fileStats.push(await writeJson("data-quality/latest.json", dataQuality));
fileStats.push(await writeJson("readiness/latest.json", readiness));
fileStats.push(await writeJson("archive-health/latest.json", archiveHealth));
fileStats.push(await writeJson("reports/index.json", {
  ...reports,
  newsletterProvider: process.env.NEWSLETTER_ENDPOINT ? "configured provider" : reports.newsletterProvider,
  signupEnabled: Boolean(process.env.NEWSLETTER_ENDPOINT),
  reports: publishedReports
}));

await rm(path.join(root, "public", "reports"), { recursive: true, force: true });
for (const report of publishedReports) {
  for (const highlight of report.indexHighlights) {
    if (!highlight.chartPath) continue;
    const source = path.join(sourceDataRoot, "report-assets", report.week, `${highlight.code}.png`);
    const destination = path.join(root, "public", highlight.chartPath.replace(/^\//, ""));
    await mkdir(path.dirname(destination), { recursive: true });
    await copyFile(source, destination);
  }
}

for (const index of indexes) {
  const summary = { ...index };
  delete summary.history;
  delete summary.constituents;
  delete summary.rebalances;
  delete summary.previewHistory;
  delete summary.previewConstituents;
  delete summary.previewRebalances;
  fileStats.push(await writeJson(`indexes/${index.code}/summary.json`, summary));
  fileStats.push(await writeJson(`indexes/${index.code}/history.json`, index.history));
  fileStats.push(await writeJson(`indexes/${index.code}/constituents.json`, index.constituents));
  fileStats.push(await writeJson(`indexes/${index.code}/preview-history.json`, index.previewHistory));
  fileStats.push(await writeJson(`indexes/${index.code}/preview-constituents.json`, index.previewConstituents));
  fileStats.push(await writeJson(
    `indexes/${index.code}/preview-rebalances.json`,
    index.previewRebalances ?? {
      schema_version: 1,
      index_code: index.code,
      data_state: "preview",
      cadence: "daily_preview",
      generated_for: index.base_date,
      rebalances: []
    }
  ));
  fileStats.push(await writeJson(
    `indexes/${index.code}/rebalances.json`,
    index.rebalances ?? deriveRebalances(index, index.constituents, sourceData.methodologyVersion)
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
