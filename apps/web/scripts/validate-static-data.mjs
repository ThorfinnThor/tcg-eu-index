import { createHash } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const dataRoot = path.join(root, "public", "data");
const sourceDataRoot = path.join(root, "source-data");
const sourceDataPath = path.join(sourceDataRoot, "indexes.json");
const seoDataRoot = path.join(root, "data-config", "seo");
const maxBytes = 1_000_000;
const preferredMaxBytes = 250_000;

function fail(message) {
  throw new Error(`static data validation failed: ${message}`);
}

async function readJson(relativePath) {
  const body = await readFile(path.join(dataRoot, relativePath), "utf8");
  return JSON.parse(body);
}

async function readSourceJson(indexCode, fileName) {
  return JSON.parse(await readFile(path.join(sourceDataRoot, "indexes", indexCode, fileName), "utf8"));
}

async function readSourceFile(relativePath) {
  return JSON.parse(await readFile(path.join(sourceDataRoot, relativePath), "utf8"));
}

async function readSeoFile(fileName) {
  return JSON.parse(await readFile(path.join(seoDataRoot, fileName), "utf8"));
}

const manifest = await readJson("manifest.json");
if (!manifest.datasetVersion || !manifest.generatedAt || manifest.schemaVersion !== 1) {
  fail("manifest is missing required version fields");
}

const sourceData = JSON.parse(await readFile(sourceDataPath, "utf8"));
if (!Array.isArray(sourceData.indexes) || sourceData.indexes.length === 0) {
  fail("source-data/indexes.json must define at least one index");
}
if (sourceData.datasetVersion !== manifest.datasetVersion) {
  fail("source data and manifest dataset versions differ");
}
for (const index of sourceData.indexes) {
  if (!index.code || !index.slug || !index.name || !index.game || !index.universe) {
    fail(`invalid source index metadata: ${JSON.stringify(index)}`);
  }
  const sourceHistory = await readSourceJson(index.code, "history.json");
  const sourceConstituents = await readSourceJson(index.code, "constituents.json");
  if (!Array.isArray(sourceHistory) || sourceHistory.length === 0) {
    fail(`${index.code} source history is empty`);
  }
  if (index.history_start_kind !== "validation" && index.history_start_kind !== "published") {
    fail(`${index.code} has invalid history_start_kind`);
  }
  if (sourceHistory[0].value_date !== index.history_start_date) {
    fail(`${index.code} history_start_date does not match its first observation`);
  }
  if (index.base_date < index.history_start_date || !sourceHistory.some((row) => row.value_date === index.base_date)) {
    fail(`${index.code} base_date must be an available observation on or after history_start_date`);
  }
  if (!Array.isArray(sourceConstituents)) {
    fail(`${index.code} source constituents must be an array`);
  }
  for (const constituent of sourceConstituents) {
    if (!Number.isInteger(constituent.cm_product_id) || !constituent.variant_key || !constituent.name || !constituent.set) {
      fail(`${index.code} has an invalid source constituent identity`);
    }
    if (!constituent.member_since || !["added", "retained", "removed"].includes(constituent.action)) {
      fail(`${index.code} has an invalid constituent lifecycle`);
    }
    if (constituent.removed_at && constituent.removed_at <= constituent.member_since) {
      fail(`${index.code} constituent removal must be after member_since`);
    }
    if (typeof constituent.liquidity_score !== "number" || typeof constituent.ref_price !== "number") {
      fail(`${index.code} constituent metrics must be numeric`);
    }
  }
}
const sourceQuality = await readSourceFile("data-quality.json");
if (!Array.isArray(sourceQuality.limitations) || !Array.isArray(sourceQuality.checks) || !Array.isArray(sourceQuality.gaps)) {
  fail("source-data/data-quality.json must define limitations, checks, and gaps arrays");
}
if (typeof sourceQuality.datasetCompleteness !== "number" || sourceQuality.datasetCompleteness < 0 || sourceQuality.datasetCompleteness > 1) {
  fail("source-data/data-quality.json datasetCompleteness must be between 0 and 1");
}
const sourceReports = await readSourceFile("reports/index.json");
if (!Array.isArray(sourceReports.reports)) {
  fail("source-data/reports/index.json must define a reports array");
}
const reportWeeks = new Set();
const reportIds = new Set();
const configuredIndexCodes = new Set(sourceData.indexes.map((index) => index.code));
for (const report of sourceReports.reports) {
  if (!/^\d{4}-W\d{2}$/.test(report.week) || !["draft", "published"].includes(report.status)) {
    fail(`invalid report identity: ${JSON.stringify(report)}`);
  }
  if (reportWeeks.has(report.week)) fail(`duplicate report week ${report.week}`);
  reportWeeks.add(report.week);
  if (!report.id || reportIds.has(report.id)) fail(`duplicate or missing report id ${report.id}`);
  reportIds.add(report.id);
  if (!Array.isArray(report.indexHighlights) || report.indexHighlights.length !== sourceData.indexes.length) {
    fail(`${report.week} must include every configured index`);
  }
  const highlightCodes = new Set(report.indexHighlights.map((highlight) => highlight.code));
  if (highlightCodes.size !== configuredIndexCodes.size || [...configuredIndexCodes].some((code) => !highlightCodes.has(code))) {
    fail(`${report.week} highlights do not match configured indexes`);
  }
  if (report.id.endsWith("-generated") && report.indexHighlights.some((highlight) =>
    typeof highlight.startValue !== "number" || typeof highlight.endValue !== "number" || typeof highlight.observations !== "number"
  )) {
    fail(`${report.week} generated highlights require values and observation counts`);
  }
  if (report.status === "published" && !report.publishedAt) fail(`${report.week} is published without publishedAt`);
}

const generatedAt = new Date(manifest.generatedAt);
if (Number.isNaN(generatedAt.valueOf())) fail("manifest generatedAt is invalid");

const indexes = await readJson("search/indexes.json");
if (!Array.isArray(indexes) || indexes.length === 0) fail("search/indexes.json is empty");
const dataQuality = await readJson("data-quality/latest.json");
if (!Array.isArray(dataQuality.checks) || !Array.isArray(dataQuality.gaps)) {
  fail("data-quality/latest.json has invalid shape");
}
const reports = await readJson("reports/index.json");
if (!Array.isArray(reports.reports)) fail("reports/index.json has invalid shape");

const keywords = await readSeoFile("keywords.json");
const pageDefinitions = await readSeoFile("page-definitions.json");
if (!Array.isArray(keywords) || !Array.isArray(pageDefinitions)) {
  fail("SEO registry files must be arrays");
}
const approvedKeywordIds = new Set(
  keywords
    .filter((keyword) => keyword.status === "approved" && keyword.validated === true)
    .map((keyword) => keyword.id)
);
for (const page of pageDefinitions.filter((definition) => definition.status === "published")) {
  if (!page.id || !page.template || typeof page.minimumDataCompleteness !== "number") {
    fail(`invalid published SEO page definition: ${JSON.stringify(page)}`);
  }
  if (!approvedKeywordIds.has(page.keywordId)) {
    fail(`${page.id} references a missing or unapproved keyword`);
  }
  if (page.indexable !== true) {
    fail(`${page.id} is published but not indexable`);
  }
}

const slugs = new Set();
for (const item of indexes) {
  if (!item.id || !item.slug || !item.name || typeof item.score !== "number") {
    fail(`invalid search record: ${JSON.stringify(item)}`);
  }
  if (slugs.has(item.slug)) fail(`duplicate slug ${item.slug}`);
  slugs.add(item.slug);
}

for (const file of manifest.files ?? []) {
  const relativePath = file.path.replace(/^data\//, "");
  const absolutePath = path.join(dataRoot, relativePath);
  const info = await stat(absolutePath);
  if (info.size > maxBytes) fail(`${file.path} exceeds ${maxBytes} bytes`);
  if (info.size > preferredMaxBytes) {
    console.warn(`${file.path} exceeds preferred ${preferredMaxBytes} byte target`);
  }
  const body = await readFile(absolutePath, "utf8");
  const checksum = createHash("sha256").update(body).digest("hex");
  if (manifest.fileChecksums[file.path] !== checksum) fail(`${file.path} checksum mismatch`);
}

for (const index of indexes) {
  const summary = await readJson(`indexes/${index.id}/summary.json`);
  const history = await readJson(`indexes/${index.id}/history.json`);
  const constituents = await readJson(`indexes/${index.id}/constituents.json`);
  if (summary.code !== index.id) fail(`${index.id} summary code mismatch`);
  if (!summary.history_start_date || !summary.history_start_kind || !summary.base_date) {
    fail(`${index.id} summary is missing history provenance`);
  }
  if (!Array.isArray(history) || history.length === 0) fail(`${index.id} history is empty`);
  if (!Array.isArray(constituents)) fail(`${index.id} constituents must be an array`);
  const constituentKeys = new Set();
  for (const constituent of constituents) {
    if (!constituent.member_since || !constituent.action || typeof constituent.ref_price !== "number") {
      fail(`${index.id} has invalid exported constituent data`);
    }
    const key = `${constituent.cm_product_id}:${constituent.variant_key}`;
    if (constituentKeys.has(key)) fail(`${index.id} has duplicate constituent ${key}`);
    constituentKeys.add(key);
  }
  let previousRow = null;
  const historyDates = new Set();
  for (const row of history) {
    if (!row.value_date || typeof row.index_value !== "number") {
      fail(`${index.id} has invalid history row`);
    }
    if (Math.abs(row.daily_return ?? 0) > 0.25) {
      fail(`${index.id} daily return exceeds methodology cap`);
    }
    if (historyDates.has(row.value_date) || (previousRow && row.value_date <= previousRow.value_date)) {
      fail(`${index.id} history dates must be unique and ascending`);
    }
    if (previousRow) {
      const impliedReturn = row.index_value / previousRow.index_value - 1;
      if (Math.abs(impliedReturn - row.daily_return) > 0.000001) {
        fail(`${index.id} daily return does not reconcile on ${row.value_date}`);
      }
    }
    historyDates.add(row.value_date);
    previousRow = row;
  }
}

const statusPayload = await readJson("status/latest.json");
if (statusPayload.gap_count !== dataQuality.gaps.length) fail("status gap_count does not match data-quality gaps");
if (statusPayload.dataset_version !== manifest.datasetVersion || statusPayload.source !== manifest.sourceVersions.source) {
  fail("status provenance does not match manifest");
}
if (!statusPayload.generated_at || Number.isNaN(new Date(statusPayload.generated_at).valueOf())) {
  fail("status generated_at is invalid");
}
const exportedLatestDates = await Promise.all(indexes.map(async (index) => {
  const history = await readJson(`indexes/${index.id}/history.json`);
  return history.at(-1)?.value_date ?? null;
}));
const expectedLatestDate = exportedLatestDates.filter(Boolean).sort().at(-1) ?? null;
if (statusPayload.last_snapshot_date !== expectedLatestDate || statusPayload.last_calc_date !== expectedLatestDate) {
  fail("status latest dates do not match exported index history");
}

console.log("static data validation passed");
