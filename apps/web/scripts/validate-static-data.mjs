import { createHash } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const dataRoot = path.join(root, "public", "data");
const sourceDataRoot = path.join(root, "source-data");
const sourceDataPath = path.join(sourceDataRoot, "indexes.json");
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
  if (!Array.isArray(sourceConstituents)) {
    fail(`${index.code} source constituents must be an array`);
  }
}

const generatedAt = new Date(manifest.generatedAt);
if (Number.isNaN(generatedAt.valueOf())) fail("manifest generatedAt is invalid");

const indexes = await readJson("search/indexes.json");
if (!Array.isArray(indexes) || indexes.length === 0) fail("search/indexes.json is empty");

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
  if (!Array.isArray(history) || history.length === 0) fail(`${index.id} history is empty`);
  if (!Array.isArray(constituents)) fail(`${index.id} constituents must be an array`);
  for (const row of history) {
    if (!row.value_date || typeof row.index_value !== "number") {
      fail(`${index.id} has invalid history row`);
    }
    if (Math.abs(row.daily_return ?? 0) > 0.25) {
      fail(`${index.id} daily return exceeds methodology cap`);
    }
  }
}

console.log("static data validation passed");
