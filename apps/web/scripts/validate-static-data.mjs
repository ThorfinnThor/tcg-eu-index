import { createHash } from "node:crypto";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const dataRoot = path.join(root, "public", "data");
const sourceDataRoot = path.join(root, "source-data");
const sourceDataPath = path.join(sourceDataRoot, "indexes.json");
const seoDataRoot = path.join(root, "data-config", "seo");
const reportsRoot = path.join(root, "generated", "reports");
const maxBytes = 1_000_000;
const preferredMaxBytes = 250_000;
const allowedRelationshipTypes = new Set(["parent", "child", "related", "comparison", "next_step"]);

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

async function fileExists(filePath) {
  return stat(filePath)
    .then(() => true)
    .catch((error) => {
      if (error?.code === "ENOENT") return false;
      throw error;
    });
}

function assertCollectorIdentity(payload, code, version, label) {
  if (
    payload.schema_version !== 2 || payload.index_code !== code ||
    payload.methodology_version !== version || payload.data_state !== "private_shadow" ||
    payload.series_id !== `${code}:${version}:private_shadow`
  ) {
    fail(`${code} ${label} has invalid collector identity`);
  }
}

async function validateCollectorPreview() {
  const collectorIndexPath = path.join(dataRoot, "collector", "index.json");
  if (!await fileExists(collectorIndexPath)) return 0;
  const collectorIndex = await readJson("collector/index.json");
  if (
    collectorIndex.schema_version !== 1 || collectorIndex.publication_state !== "preview_noindex" ||
    !/^\d{4}-\d{2}-\d{2}$/.test(collectorIndex.generated_for) ||
    typeof collectorIndex.methodology_version !== "string" || !Array.isArray(collectorIndex.indexes) ||
    collectorIndex.indexes.length === 0
  ) {
    fail("collector preview index has an invalid publication contract");
  }
  const seenCodes = new Set();
  for (const item of collectorIndex.indexes) {
    const code = item.code;
    if (
      typeof code !== "string" || !/^[A-Z]+COL$/.test(code) || code.endsWith("SCOL") ||
      seenCodes.has(code) || !item.name || !item.game_key ||
      !["accumulating", "preview"].includes(item.status) ||
      typeof item.base_value !== "number" || !Number.isFinite(item.base_value) || item.base_value <= 0 ||
      !Number.isInteger(item.constituent_count)
    ) {
      fail(`invalid collector preview record: ${JSON.stringify(item)}`);
    }
    seenCodes.add(code);
    const payloads = Object.fromEntries(await Promise.all(
      ["manifest", "summary", "history", "rebalances", "diagnostics", "composition"].map(async (name) => [
        name,
        await readJson(`collector/${code}/${name}.json`)
      ])
    ));
    for (const [label, payload] of Object.entries(payloads)) {
      assertCollectorIdentity(payload, code, collectorIndex.methodology_version, label);
    }
    if (
      payloads.manifest.public_alias_enabled !== false ||
      payloads.manifest.publication_state !== "preview_noindex" ||
      payloads.summary.public_alias_enabled !== false || payloads.summary.universe !== "singles" ||
      payloads.diagnostics.publication_state !== "preview_noindex" ||
      !Array.isArray(payloads.diagnostics.eligibility) || payloads.diagnostics.eligibility.length !== 0 ||
      !Array.isArray(payloads.history.records) || !Array.isArray(payloads.rebalances.rebalances) ||
      payloads.composition.publication_state !== "preview_noindex" || !Array.isArray(payloads.composition.rebalances)
    ) {
      fail(`${code} is not a bounded singles-only noindex preview`);
    }
    const latestRebalance = payloads.rebalances.rebalances.at(-1);
    if ((latestRebalance?.active_count ?? 0) !== item.constituent_count) {
      fail(`${code} constituent count does not match its latest rebalance`);
    }
    const outputEntries = Object.entries(payloads.manifest.outputs ?? {});
    const expectedOutputFiles = new Set([
      "summary.json", "history.json", "rebalances.json", "diagnostics.json", "composition.json"
    ]);
    if (outputEntries.length !== expectedOutputFiles.size) {
      fail(`${code} collector manifest must expose exactly four bounded outputs`);
    }
    for (const [logicalKey, metadata] of outputEntries) {
      const fileName = logicalKey.endsWith("public-preview.json")
        ? "diagnostics.json"
        : logicalKey.split("/").at(-1);
      if (!expectedOutputFiles.delete(fileName)) {
        fail(`${code} collector manifest exposes an unexpected output ${logicalKey}`);
      }
      const body = await readFile(path.join(dataRoot, "collector", code, fileName));
      const checksum = createHash("sha256").update(body).digest("hex");
      if (metadata.sha256 !== checksum || metadata.bytes !== body.byteLength) {
        fail(`${code} ${fileName} does not match its collector manifest`);
      }
    }
    if (expectedOutputFiles.size !== 0) fail(`${code} collector manifest is incomplete`);
    if (payloads.rebalances.rebalances.some((rebalance) => !Array.isArray(rebalance.constituents) || rebalance.constituents.length !== 0)) {
      fail(`${code} rebalances must not embed the full public composition`);
    }
    const compositionByDate = new Map(
      payloads.composition.rebalances.map((rebalance) => [rebalance.effective_date, rebalance])
    );
    if (compositionByDate.size !== payloads.rebalances.rebalances.length) {
      fail(`${code} composition dates do not match rebalances`);
    }
    for (const rebalance of payloads.rebalances.rebalances) {
      const compositionRecord = compositionByDate.get(rebalance.effective_date);
      if (
        !compositionRecord || compositionRecord.active_count !== rebalance.active_count ||
        !Number.isInteger(compositionRecord.page_size) || compositionRecord.page_size < 1 ||
        !Number.isInteger(compositionRecord.page_count) || compositionRecord.page_count < 1 ||
        !Array.isArray(compositionRecord.pages) || compositionRecord.pages.length !== compositionRecord.page_count
      ) {
        fail(`${code} has invalid composition pagination for ${rebalance.effective_date}`);
      }
      let constituentCount = 0;
      let previousPrice = Number.NEGATIVE_INFINITY;
      for (const [pageIndex, pageMetadata] of compositionRecord.pages.entries()) {
        if (
          pageMetadata.page !== pageIndex + 1 ||
          !new RegExp(`^composition/${rebalance.effective_date}/\\d{4}\\.json$`).test(pageMetadata.path)
        ) {
          fail(`${code} has an invalid composition page path`);
        }
        const pagePath = path.join(dataRoot, "collector", code, pageMetadata.path);
        const body = await readFile(pagePath);
        const checksum = createHash("sha256").update(body).digest("hex");
        if (pageMetadata.sha256 !== checksum || pageMetadata.bytes !== body.byteLength) {
          fail(`${code} composition page ${pageMetadata.page} checksum mismatch`);
        }
        const page = JSON.parse(body.toString("utf8"));
        assertCollectorIdentity(page, code, collectorIndex.methodology_version, "composition page");
        if (
          page.publication_state !== "preview_noindex" || page.effective_date !== rebalance.effective_date ||
          page.page !== pageMetadata.page || page.page_count !== compositionRecord.page_count ||
          !Array.isArray(page.constituents) || page.constituents.length > compositionRecord.page_size
        ) {
          fail(`${code} composition page ${pageMetadata.page} has an invalid contract`);
        }
        for (const member of page.constituents) {
          if (
            typeof member.selection_price !== "number" || !Number.isFinite(member.selection_price) ||
            member.selection_price < previousPrice
          ) {
            fail(`${code} composition is not globally sorted by ascending price on ${rebalance.effective_date}`);
          }
          previousPrice = member.selection_price;
        }
        constituentCount += page.constituents.length;
      }
      if (constituentCount !== rebalance.active_count) {
        fail(`${code} paginated composition does not reconcile on ${rebalance.effective_date}`);
      }
    }
  }
  return collectorIndex.indexes.length;
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
  if (!Array.isArray(sourceHistory)) fail(`${index.code} source history must be an array`);
  if (!["accumulating", "preview", "published"].includes(index.status)) {
    fail(`${index.code} has invalid status`);
  }
  if (!["validation", "preview", "published"].includes(index.history_start_kind)) {
    fail(`${index.code} has invalid history_start_kind`);
  }
  if (
    ["preview", "published"].includes(index.status) &&
    index.status !== index.history_start_kind
  ) {
    fail(`${index.code} status does not match history_start_kind`);
  }
  if (["preview", "published"].includes(index.status) && sourceHistory.length === 0) {
    fail(`${index.code} visible source history is empty`);
  }
  if (sourceHistory.length > 0) {
    if (sourceHistory[0].value_date !== index.history_start_date) {
      fail(`${index.code} history_start_date does not match its first observation`);
    }
    if (index.base_date < index.history_start_date || !sourceHistory.some((row) => row.value_date === index.base_date)) {
      fail(`${index.code} base_date must be an available observation on or after history_start_date`);
    }
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
    if (constituent.entry_reason !== undefined && typeof constituent.entry_reason !== "string") {
      fail(`${index.code} constituent entry_reason must be a string`);
    }
    if (constituent.removal_reason !== undefined && typeof constituent.removal_reason !== "string") {
      fail(`${index.code} constituent removal_reason must be a string`);
    }
  }
}
const sourceQuality = await readSourceFile("data-quality.json");
if (!Array.isArray(sourceQuality.limitations) || !Array.isArray(sourceQuality.checks) || !Array.isArray(sourceQuality.gaps)) {
  fail("source-data/data-quality.json must define limitations, checks, and gaps arrays");
}
const sourceArchiveHealth = await readSourceFile("archive-health.json");
if (
  sourceArchiveHealth.schemaVersion !== 1 ||
  !["pending_first_audit", "healthy", "attention_required"].includes(sourceArchiveHealth.status) ||
  !Array.isArray(sourceArchiveHealth.gaps) ||
  typeof sourceArchiveHealth.storage !== "object" ||
  typeof sourceArchiveHealth.operations !== "object" ||
  typeof sourceArchiveHealth.cutoverProjection !== "object"
) {
  fail("source-data/archive-health.json has an invalid contract");
}
if (
  sourceArchiveHealth.coverageRatio !== null &&
  (typeof sourceArchiveHealth.coverageRatio !== "number" || sourceArchiveHealth.coverageRatio < 0 || sourceArchiveHealth.coverageRatio > 1)
) {
  fail("archive health coverageRatio must be null or between 0 and 1");
}
if (sourceArchiveHealth.gapCount !== null && sourceArchiveHealth.gapCount !== sourceArchiveHealth.gaps.length) {
  fail("archive health gapCount does not match gaps");
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
const sourceReadiness = await readSourceFile("readiness.json");
if (
  sourceReadiness.schemaVersion !== 1 || sourceReadiness.methodologyVersion !== sourceData.methodologyVersion ||
  sourceReadiness.publicationStatus !== "blocked_until_human_cutover" || sourceReadiness.humanReviewRequired !== true ||
  !["collecting", "eligible_for_human_review"].includes(sourceReadiness.state) || !Array.isArray(sourceReadiness.indexes)
) {
  fail("source-data/readiness.json has an invalid top-level contract");
}
if (sourceReadiness.generatedFor !== null && !/^\d{4}-\d{2}-\d{2}$/.test(sourceReadiness.generatedFor)) {
  fail("readiness generatedFor must be null or an ISO date");
}
const readinessCodes = new Set(sourceReadiness.indexes.map((item) => item.code));
if (
  readinessCodes.size !== configuredIndexCodes.size ||
  [...configuredIndexCodes].some((code) => !readinessCodes.has(code))
) {
  fail("readiness indexes do not match configured indexes");
}
for (const item of sourceReadiness.indexes) {
  if (
    !["pending_receipt", "accumulating", "eligible_for_human_review"].includes(item.state) ||
    !Number.isInteger(item.requiredLookbackDays) || !Number.isInteger(item.targetSize) ||
    (item.availableArchiveDays !== null && !Number.isInteger(item.availableArchiveDays)) ||
    (item.daysRemaining !== null && !Number.isInteger(item.daysRemaining)) ||
    (item.selectedConstituents !== null && !Number.isInteger(item.selectedConstituents)) ||
    item.languageScope !== "all-cardmarket-europe-languages" ||
    typeof item.gates !== "object" || item.gates === null || !Array.isArray(item.blockers)
  ) {
    fail(`invalid readiness item: ${JSON.stringify(item)}`);
  }
}
for (const report of sourceReports.reports) {
  if (!/^\d{4}-W\d{2}$/.test(report.week) || !["draft", "published"].includes(report.status)) {
    fail(`invalid report identity: ${JSON.stringify(report)}`);
  }
  if (reportWeeks.has(report.week)) fail(`duplicate report week ${report.week}`);
  reportWeeks.add(report.week);
  if (!report.id || reportIds.has(report.id)) fail(`duplicate or missing report id ${report.id}`);
  reportIds.add(report.id);
  if (!Array.isArray(report.indexHighlights)) fail(`${report.week} indexHighlights must be an array`);
  const highlightCodes = new Set(report.indexHighlights.map((highlight) => highlight.code));
  if (report.status === "published" && (
    highlightCodes.size !== configuredIndexCodes.size || [...configuredIndexCodes].some((code) => !highlightCodes.has(code))
  )) {
    fail(`${report.week} highlights do not match configured indexes`);
  }
  if (report.id.endsWith("-generated") && report.indexHighlights.some((highlight) =>
    typeof highlight.startValue !== "number" || typeof highlight.endValue !== "number" || typeof highlight.observations !== "number"
  )) {
    fail(`${report.week} generated highlights require values and observation counts`);
  }
  if (report.status === "published" && !report.publishedAt) fail(`${report.week} is published without publishedAt`);
  for (const highlight of report.indexHighlights) {
    if (highlight.chartPath !== undefined) {
      const expectedPath = `/reports/${report.week}/${highlight.code}.png`;
      if (highlight.chartPath !== expectedPath) fail(`${report.week} has invalid chart path ${highlight.chartPath}`);
      if (report.status === "published") {
        await stat(path.join(sourceDataRoot, "report-assets", report.week, `${highlight.code}.png`)).catch(() => {
          fail(`${report.week} is published without chart ${highlight.chartPath}`);
        });
      }
    }
  }
}

const generatedAt = new Date(manifest.generatedAt);
if (Number.isNaN(generatedAt.valueOf())) fail("manifest generatedAt is invalid");
const collectorPreviewCount = await validateCollectorPreview();

const indexes = await readJson("search/indexes.json");
if (!Array.isArray(indexes) || indexes.length === 0) fail("search/indexes.json is empty");
const dataQuality = await readJson("data-quality/latest.json");
if (!Array.isArray(dataQuality.checks) || !Array.isArray(dataQuality.gaps)) {
  fail("data-quality/latest.json has invalid shape");
}
const readiness = await readJson("readiness/latest.json");
if (JSON.stringify(readiness) !== JSON.stringify(sourceReadiness)) {
  fail("readiness/latest.json does not match its source contract");
}
const archiveHealth = await readJson("archive-health/latest.json");
if (JSON.stringify(archiveHealth) !== JSON.stringify(sourceArchiveHealth)) {
  fail("archive-health/latest.json does not match its source contract");
}
const reports = await readJson("reports/index.json");
if (!Array.isArray(reports.reports)) fail("reports/index.json has invalid shape");

const keywords = await readSeoFile("keywords.json");
const pageDefinitions = await readSeoFile("page-definitions.json");
if (!Array.isArray(keywords) || !Array.isArray(pageDefinitions)) {
  fail("SEO registry files must be arrays");
}
const keywordsById = new Map();
for (const keyword of keywords) {
  if (
    !keyword.id || !keyword.keyword || !keyword.locale || !keyword.market || !keyword.intent || !keyword.cluster ||
    typeof keyword.priority !== "number" || typeof keyword.validated !== "boolean" || !keyword.status
  ) {
    fail(`invalid SEO keyword: ${JSON.stringify(keyword)}`);
  }
  if (keywordsById.has(keyword.id)) fail(`duplicate keyword id ${keyword.id}`);
  if (!Array.isArray(keyword.evidence) || keyword.evidence.length === 0) {
    fail(`${keyword.id} must record demand evidence`);
  }
  keywordsById.set(keyword.id, keyword);
}

const pageDefinitionsById = new Map();
const pageSlugs = new Set();
const pageCanonicals = new Set();
const indexableKeywordIds = new Set();
for (const page of pageDefinitions) {
  if (
    !page.id || !page.linkLabel || typeof page.slug !== "string" || !page.keywordId || !page.locale || !page.intent || !page.cluster ||
    !page.template || typeof page.minimumResults !== "number" ||
    typeof page.minimumDataCompleteness !== "number" || typeof page.minimumInsights !== "number" ||
    !page.canonical || typeof page.indexable !== "boolean" || !["draft", "published", "retired"].includes(page.status)
  ) {
    fail(`invalid SEO page definition: ${JSON.stringify(page)}`);
  }
  if (pageDefinitionsById.has(page.id)) fail(`duplicate page definition id ${page.id}`);
  if (pageSlugs.has(page.slug)) fail(`duplicate page definition slug ${page.slug}`);
  if (pageCanonicals.has(page.canonical)) fail(`duplicate canonical ${page.canonical}`);
  const expectedCanonical = page.slug ? `/${page.slug}` : "/";
  if (page.canonical !== expectedCanonical) fail(`${page.id} canonical does not match its slug`);
  if (page.minimumResults < 0 || page.minimumInsights < 0) fail(`${page.id} has a negative quality threshold`);
  if (page.minimumDataCompleteness < 0 || page.minimumDataCompleteness > 1) {
    fail(`${page.id} minimumDataCompleteness must be between 0 and 1`);
  }
  if (!Array.isArray(page.relationships)) fail(`${page.id} relationships must be an array`);
  if (page.indexable && page.status !== "published") fail(`${page.id} is indexable without published status`);
  const keyword = keywordsById.get(page.keywordId);
  if (!keyword) fail(`${page.id} references missing keyword ${page.keywordId}`);
  if (page.locale !== keyword.locale || page.intent !== keyword.intent || page.cluster !== keyword.cluster) {
    fail(`${page.id} does not match its keyword locale, intent, and cluster`);
  }
  if (page.indexable) {
    if (keyword.status !== "approved" || keyword.validated !== true) {
      fail(`${page.id} references an unapproved keyword`);
    }
    if (indexableKeywordIds.has(page.keywordId)) {
      fail(`${page.id} reuses indexable keyword ${page.keywordId} and creates a cannibalization risk`);
    }
    indexableKeywordIds.add(page.keywordId);
  }
  pageDefinitionsById.set(page.id, page);
  pageSlugs.add(page.slug);
  pageCanonicals.add(page.canonical);
}

for (const page of pageDefinitions) {
  for (const relationship of page.relationships) {
    if (!allowedRelationshipTypes.has(relationship.type) || !pageDefinitionsById.has(relationship.targetId)) {
      fail(`${page.id} has an invalid relationship ${JSON.stringify(relationship)}`);
    }
    if (relationship.targetId === page.id) fail(`${page.id} cannot link to itself`);
  }
  if (page.indexable && page.id !== "overview" && !page.relationships.some((relationship) => relationship.type === "parent")) {
    fail(`${page.id} is an orphan without a parent relationship`);
  }
}

const publishedReportCount = sourceReports.reports.filter((report) => report.status === "published").length;
function pageQuality(page) {
  if (page.template === "market-overview") {
    return { resultCount: sourceData.indexes.length, insightCount: sourceData.indexes.length };
  }
  if (page.template === "index-detail") {
    const code = page.filters?.code;
    const index = sourceData.indexes.find((candidate) => candidate.code === code);
    return { resultCount: index ? 1 : 0, insightCount: index ? 3 : 0 };
  }
  if (page.template === "methodology") return { resultCount: 1, insightCount: 1 };
  if (page.template === "report-archive") {
    return { resultCount: publishedReportCount, insightCount: publishedReportCount };
  }
  if (page.template === "data-quality") {
    return { resultCount: sourceQuality.checks.length, insightCount: sourceQuality.limitations.length };
  }
  return { resultCount: 0, insightCount: 0 };
}

for (const page of pageDefinitions.filter((definition) => definition.indexable)) {
  const quality = pageQuality(page);
  if (quality.resultCount < page.minimumResults) {
    fail(`${page.id} has ${quality.resultCount} results but requires ${page.minimumResults}`);
  }
  if (quality.insightCount < page.minimumInsights) {
    fail(`${page.id} has ${quality.insightCount} insights but requires ${page.minimumInsights}`);
  }
  if (sourceQuality.datasetCompleteness < page.minimumDataCompleteness) {
    fail(`${page.id} fails its minimum data completeness threshold`);
  }
}

const slugs = new Set();
for (const item of indexes) {
  const published = ["preview", "published"].includes(item.filterValues?.status);
  if (
    !item.id || !item.slug || !item.name ||
    (published ? typeof item.score !== "number" : item.score !== null)
  ) {
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
  const rebalances = await readJson(`indexes/${index.id}/rebalances.json`);
  if (summary.code !== index.id) fail(`${index.id} summary code mismatch`);
  if (!summary.history_start_date || !summary.history_start_kind || !summary.base_date) {
    fail(`${index.id} summary is missing history provenance`);
  }
  if (!Array.isArray(history)) fail(`${index.id} history must be an array`);
  if (!Array.isArray(constituents)) fail(`${index.id} constituents must be an array`);
  const visible = ["preview", "published"].includes(summary.status);
  if (visible && (history.length === 0 || constituents.length === 0)) {
    fail(`${index.id} visible data must include history and constituents`);
  }
  if (!visible && (history.length > 0 || constituents.length > 0)) {
    fail(`${index.id} accumulating data must not expose validation history or constituents`);
  }
  if (
    rebalances.schema_version !== 1 || rebalances.index_code !== index.id ||
    !["monthly", "daily_preview"].includes(rebalances.cadence) ||
    !["validation", "preview", "published"].includes(rebalances.data_state) || !Array.isArray(rebalances.rebalances)
  ) {
    fail(`${index.id} rebalances have an invalid contract`);
  }
  if (
    rebalances.data_state !== summary.history_start_kind ||
    !rebalances.generated_for
  ) {
    fail(`${index.id} rebalance provenance does not match its summary`);
  }
  const constituentKeys = new Set();
  for (const constituent of constituents) {
    if (!constituent.member_since || !constituent.action || typeof constituent.ref_price !== "number") {
      fail(`${index.id} has invalid exported constituent data`);
    }
    const key = `${constituent.cm_product_id}:${constituent.variant_key}:${constituent.member_since}`;
    if (constituentKeys.has(key)) fail(`${index.id} has duplicate constituent ${key}`);
    constituentKeys.add(key);
  }
  let previousRebalanceDate = null;
  for (const rebalance of rebalances.rebalances) {
    if (
      !rebalance.effective_date || !rebalance.methodology_version ||
      !Number.isInteger(rebalance.active_count) || !Number.isInteger(rebalance.retained_count) ||
      !Array.isArray(rebalance.changes)
    ) {
      fail(`${index.id} has an invalid rebalance record`);
    }
    if (previousRebalanceDate && rebalance.effective_date <= previousRebalanceDate) {
      fail(`${index.id} rebalance dates must be unique and ascending`);
    }
    const activeCount = constituents.filter((item) =>
      item.member_since <= rebalance.effective_date && (!item.removed_at || item.removed_at > rebalance.effective_date)
    ).length;
    if (rebalance.active_count !== activeCount) {
      fail(`${index.id} rebalance active_count does not reconcile on ${rebalance.effective_date}`);
    }
    const additions = rebalance.changes.filter((change) => change.action === "added");
    if (rebalance.retained_count !== Math.max(activeCount - additions.length, 0)) {
      fail(`${index.id} rebalance retained_count does not reconcile on ${rebalance.effective_date}`);
    }
    for (const change of rebalance.changes) {
      if (
        !Number.isInteger(change.cm_product_id) || !change.variant_key ||
        !["added", "removed"].includes(change.action) || !change.reason
      ) {
        fail(`${index.id} has an invalid rebalance change`);
      }
      const matchingLifecycle = constituents.some((item) =>
        item.cm_product_id === change.cm_product_id && item.variant_key === change.variant_key &&
        (change.action === "added" ? item.member_since === rebalance.effective_date : item.removed_at === rebalance.effective_date)
      );
      if (!matchingLifecycle) {
        fail(`${index.id} rebalance change does not match constituent lifecycle`);
      }
    }
    previousRebalanceDate = rebalance.effective_date;
  }
  if (rebalances.rebalances.length && rebalances.generated_for !== rebalances.rebalances.at(-1).effective_date) {
    fail(`${index.id} rebalance generated_for does not match its latest event`);
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
const expectedLatestDate = sourceReadiness.generatedFor ?? exportedLatestDates.filter(Boolean).sort().at(-1) ?? null;
if (statusPayload.last_snapshot_date !== expectedLatestDate || statusPayload.last_calc_date !== expectedLatestDate) {
  fail("status latest dates do not match readiness or exported index history");
}

const totalPublicJsonBytes = (manifest.files ?? []).reduce((total, file) => total + file.bytes, 0);
const largestPublicFile = [...(manifest.files ?? [])].sort((left, right) => right.bytes - left.bytes)[0] ?? null;
const buildReport = {
  generatedAt: new Date().toISOString(),
  datasetVersion: manifest.datasetVersion,
  publicData: {
    fileCount: manifest.files?.length ?? 0,
    totalBytes: totalPublicJsonBytes,
    largestFile: largestPublicFile ? { path: largestPublicFile.path, bytes: largestPublicFile.bytes } : null,
    preferredMaxBytes,
    hardMaxBytes: maxBytes
  },
  seo: {
    keywordCount: keywords.length,
    pageCount: pageDefinitions.length,
    indexableCount: pageDefinitions.filter((page) => page.indexable).length,
    noindexCount: pageDefinitions.filter((page) => !page.indexable).length,
    skippedPages: pageDefinitions.filter((page) => page.status === "retired").map((page) => page.id),
    duplicateCandidates: [],
    failedQualityChecks: []
  },
  collectorPreview: {
    indexCount: collectorPreviewCount,
    publicationState: collectorPreviewCount > 0 ? "preview_noindex" : "not_exported"
  }
};
await mkdir(reportsRoot, { recursive: true });
await writeFile(path.join(reportsRoot, "static-build.json"), `${JSON.stringify(buildReport, null, 2)}\n`);

console.log(
  `static data validation passed: ${buildReport.publicData.fileCount} files, ${buildReport.publicData.totalBytes} bytes, ` +
  `${buildReport.seo.indexableCount} indexable pages, ${buildReport.seo.noindexCount} noindex pages`
);
