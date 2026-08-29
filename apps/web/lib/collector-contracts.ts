import type {
  CollectorDataState,
  CollectorDiagnostics,
  CollectorHistory,
  CollectorIndexCode,
  CollectorPreviewIndexPayload,
  CollectorIndexSummary,
  CollectorOutputManifest,
  CollectorRebalances
} from "./types";

type JsonObject = Record<string, unknown>;

const collectorIndexCodes = new Set([
  "MTEUCOL", "MTEUSCOL", "YGEUCOL", "YGEUSCOL", "OPEUCOL", "OPEUSCOL",
  "PKEUCOL", "PKEUSCOL", "DBSEUCOL", "DBSEUSCOL", "FABEUCOL", "FABEUSCOL",
  "DGEUCOL", "DGEUSCOL", "LCEUCOL", "LCEUSCOL", "SWUEUCOL", "SWUEUSCOL",
  "RBEUCOL", "RBEUSCOL"
]);

function object(value: unknown, label: string): JsonObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as JsonObject;
}

function string(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) throw new Error(`${label} must be a string`);
  return value;
}

function isoDate(value: unknown, label: string): string {
  const text = string(value, label);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) throw new Error(`${label} must be an ISO date`);
  return text;
}

function integer(value: unknown, label: string): number {
  if (!Number.isInteger(value)) throw new Error(`${label} must be an integer`);
  return value as number;
}

function number(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${label} must be numeric`);
  return value;
}

function array(value: unknown, label: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  return value;
}

function identity(payload: JsonObject, expected: { code: string; version: string; series: string }, label: string) {
  if (payload.schema_version !== 2) throw new Error(`${label} must use schema v2`);
  if (payload.index_code !== expected.code) throw new Error(`${label} has an inconsistent index code`);
  if (payload.methodology_version !== expected.version) throw new Error(`${label} has an inconsistent methodology version`);
  if (payload.series_id !== expected.series) throw new Error(`${label} has an inconsistent series id`);
  if (payload.data_state !== "private_shadow") throw new Error(`${label} must be private_shadow`);
  if (!expected.series.endsWith(":private_shadow")) throw new Error(`${label} has a non-private series id`);
}

function code(value: unknown, label: string): CollectorIndexCode {
  const text = string(value, label);
  if (!collectorIndexCodes.has(text)) {
    throw new Error(`${label} is not a number-free collector index code`);
  }
  return text as CollectorIndexCode;
}

export function validateCollectorManifest(value: unknown): asserts value is CollectorOutputManifest {
  const payload = object(value, "collector manifest");
  const indexCode = code(payload.index_code, "collector manifest.index_code");
  const version = string(payload.methodology_version, "collector manifest.methodology_version");
  const series = string(payload.series_id, "collector manifest.series_id");
  identity(payload, { code: indexCode, version, series }, "collector manifest");
  if (payload.public_alias_enabled !== false) throw new Error("collector manifest cannot enable a public alias");
  isoDate(payload.generated_for, "collector manifest.generated_for");
  string(payload.engine_revision, "collector manifest.engine_revision");
  object(payload.source_hashes, "collector manifest.source_hashes");
  const outputs = object(payload.outputs, "collector manifest.outputs");
  if (Object.keys(outputs).length === 0) throw new Error("collector manifest.outputs cannot be empty");
  for (const [key, metadataValue] of Object.entries(outputs)) {
    if (!key.startsWith("derived/indexes/") && !key.startsWith("derived/diagnostics/")) {
      throw new Error(`collector output escaped private namespaces: ${key}`);
    }
    if (key.startsWith("derived/indexes/") && !key.includes("/private_shadow/")) {
      throw new Error(`collector index output is not private_shadow: ${key}`);
    }
    const metadata = object(metadataValue, `collector manifest.outputs.${key}`);
    if (metadata.key !== key) throw new Error(`collector manifest output key mismatch: ${key}`);
    string(metadata.sha256, `collector manifest.outputs.${key}.sha256`);
    number(metadata.bytes, `collector manifest.outputs.${key}.bytes`);
  }
}

export function validateCollectorSummary(value: unknown): asserts value is CollectorIndexSummary {
  const payload = object(value, "collector summary");
  const indexCode = code(payload.index_code, "collector summary.index_code");
  const version = string(payload.methodology_version, "collector summary.methodology_version");
  const series = string(payload.series_id, "collector summary.series_id");
  identity(payload, { code: indexCode, version, series }, "collector summary");
  if (payload.public_alias_enabled !== false || payload.target_size !== null) {
    throw new Error("collector summary must have public_alias_enabled=false and target_size=null");
  }
  string(payload.name, "collector summary.name");
  string(payload.game_key, "collector summary.game_key");
  if (payload.universe !== "singles" && payload.universe !== "sealed") throw new Error("collector summary has invalid universe");
  number(payload.base_value, "collector summary.base_value");
  if (payload.status !== "accumulating" && payload.status !== "preview") throw new Error("collector summary has invalid status");
  for (const field of ["history_start_date", "latest_value_date", "latest_rebalance"]) {
    if (payload[field] !== null) isoDate(payload[field], `collector summary.${field}`);
  }
  if (payload.latest_index_value !== null) number(payload.latest_index_value, "collector summary.latest_index_value");
  const productMetadata = object(payload.product_metadata, "collector summary.product_metadata");
  for (const field of ["constituent_count", "named_count", "set_name_count", "collector_number_count", "image_count"]) {
    integer(productMetadata[field], `collector summary.product_metadata.${field}`);
  }
  isoDate(payload.generated_for, "collector summary.generated_for");
}

export function validateCollectorHistory(value: unknown): asserts value is CollectorHistory {
  const payload = object(value, "collector history");
  const indexCode = code(payload.index_code, "collector history.index_code");
  const version = string(payload.methodology_version, "collector history.methodology_version");
  const series = string(payload.series_id, "collector history.series_id");
  identity(payload, { code: indexCode, version, series }, "collector history");
  isoDate(payload.generated_for, "collector history.generated_for");
  for (const [index, rowValue] of array(payload.records, "collector history.records").entries()) {
    const row = object(rowValue, `collector history.records[${index}]`);
    isoDate(row.value_date, "collector history value_date");
    if (row.index_value !== null) number(row.index_value, "collector history index_value");
    if (row.daily_return !== null) number(row.daily_return, "collector history daily_return");
    for (const field of ["constituent_count", "fresh_count", "capped_count", "carried_count", "suspended_count"]) integer(row[field], `collector history ${field}`);
    for (const field of ["capped_weight_share", "carried_weight_share", "suspended_weight_share", "largest_end_weight"]) number(row[field], `collector history ${field}`);
    if (row.status !== "active" && row.status !== "empty_eligible_universe") throw new Error("collector history has invalid status");
    isoDate(row.rebalance_effective_date, "collector history rebalance_effective_date");
    isoDate(row.selection_as_of, "collector history selection_as_of");
    if (row.methodology_version !== version) throw new Error("collector history row has inconsistent methodology version");
  }
}

export function validateCollectorRebalances(value: unknown): asserts value is CollectorRebalances {
  const payload = object(value, "collector rebalances");
  const indexCode = code(payload.index_code, "collector rebalances.index_code");
  const version = string(payload.methodology_version, "collector rebalances.methodology_version");
  const series = string(payload.series_id, "collector rebalances.series_id");
  identity(payload, { code: indexCode, version, series }, "collector rebalances");
  if (payload.cadence !== "monthly") throw new Error("collector rebalances must be monthly");
  isoDate(payload.generated_for, "collector rebalances.generated_for");
  for (const [index, rebalanceValue] of array(payload.rebalances, "collector rebalances.rebalances").entries()) {
    const rebalance = object(rebalanceValue, `collector rebalances[${index}]`);
    const effectiveDate = isoDate(rebalance.effective_date, "collector rebalance effective_date");
    const selectionAsOf = isoDate(rebalance.selection_as_of, "collector rebalance selection_as_of");
    if (selectionAsOf >= effectiveDate) throw new Error("collector selection_as_of must precede effective_date");
    if (rebalance.methodology_version !== version) throw new Error("collector rebalance has inconsistent methodology version");
    string(rebalance.selection_snapshot_sha256, "collector rebalance selection_snapshot_sha256");
    integer(rebalance.eligible_count, "collector rebalance eligible_count");
    integer(rebalance.active_count, "collector rebalance active_count");
    for (const [memberIndex, memberValue] of array(rebalance.constituents, "collector rebalance constituents").entries()) {
      const member = object(memberValue, `collector rebalance constituents[${memberIndex}]`);
      integer(member.cm_product_id, "collector constituent cm_product_id");
      string(member.variant_key, "collector constituent variant_key");
      string(member.stable_variant_id, "collector constituent stable_variant_id");
      number(member.selection_price, "collector constituent selection_price");
      string(member.name, "collector constituent name");
      string(member.metadata_status, "collector constituent metadata_status");
      for (const field of ["set_name", "collector_number", "image_url", "image_source", "tcgplayer_product_url"]) {
        if (member[field] !== null) string(member[field], `collector constituent ${field}`);
      }
      if (member.cm_expansion_id !== null) integer(member.cm_expansion_id, "collector constituent cm_expansion_id");
      if (member.image_url !== null && !String(member.image_url).startsWith("https://")) {
        throw new Error("collector constituent image_url must use HTTPS");
      }
      if (member.tcgplayer_product_url !== null && !String(member.tcgplayer_product_url).startsWith("https://www.tcgplayer.com/")) {
        throw new Error("collector constituent tcgplayer_product_url must use TCGplayer HTTPS");
      }
    }
  }
}

export function validateCollectorDiagnostics(value: unknown): asserts value is CollectorDiagnostics {
  const payload = object(value, "collector diagnostics");
  const indexCode = code(payload.index_code, "collector diagnostics.index_code");
  const version = string(payload.methodology_version, "collector diagnostics.methodology_version");
  const series = string(payload.series_id, "collector diagnostics.series_id");
  identity(payload, { code: indexCode, version, series }, "collector diagnostics");
  isoDate(payload.generated_for, "collector diagnostics.generated_for");
  array(payload.daily, "collector diagnostics.daily");
  array(payload.eligibility, "collector diagnostics.eligibility");
  if (payload.summary !== undefined) {
    const summary = object(payload.summary, "collector diagnostics.summary");
    integer(summary.count, "collector diagnostics.summary.count");
    integer(summary.positive_activity_rows, "collector diagnostics.summary.positive_activity_rows");
    for (const field of ["average_quality", "average_activity_ratio"]) {
      if (summary[field] !== null) number(summary[field], `collector diagnostics.summary.${field}`);
    }
  }
}

export function validateCollectorPreviewIndex(
  value: unknown
): asserts value is CollectorPreviewIndexPayload {
  const payload = object(value, "collector preview index");
  if (payload.schema_version !== 1 || payload.publication_state !== "preview_noindex") {
    throw new Error("collector preview index has an invalid publication contract");
  }
  isoDate(payload.generated_for, "collector preview index.generated_for");
  string(payload.methodology_version, "collector preview index.methodology_version");
  for (const [index, itemValue] of array(payload.indexes, "collector preview index.indexes").entries()) {
    const item = object(itemValue, `collector preview index.indexes[${index}]`);
    const indexCode = code(item.code, "collector preview index code");
    if (indexCode.endsWith("SCOL")) throw new Error("sealed collector previews cannot be published");
    string(item.name, "collector preview index name");
    string(item.game_key, "collector preview index game_key");
    if (item.status !== "accumulating" && item.status !== "preview") {
      throw new Error("collector preview index has an invalid status");
    }
    if (item.latest_index_value !== null) number(item.latest_index_value, "collector preview latest value");
    if (item.latest_value_date !== null) isoDate(item.latest_value_date, "collector preview latest date");
    integer(item.constituent_count, "collector preview constituent count");
  }
}

export function validateCollectorDataset(value: {
  manifest: unknown;
  summary: unknown;
  history: unknown;
  rebalances: unknown;
  diagnostics: unknown;
}): asserts value is {
  manifest: CollectorOutputManifest;
  summary: CollectorIndexSummary;
  history: CollectorHistory;
  rebalances: CollectorRebalances;
  diagnostics: CollectorDiagnostics;
} {
  validateCollectorManifest(value.manifest);
  validateCollectorSummary(value.summary);
  validateCollectorHistory(value.history);
  validateCollectorRebalances(value.rebalances);
  validateCollectorDiagnostics(value.diagnostics);
  const manifest = value.manifest;
  for (const payload of [value.summary, value.history, value.rebalances, value.diagnostics]) {
    const item = object(payload, "collector dataset object");
    if (item.series_id !== manifest.series_id || item.index_code !== manifest.index_code || item.methodology_version !== manifest.methodology_version) {
      throw new Error("collector dataset objects do not share manifest identity");
    }
  }
}

export const collectorDataState: CollectorDataState = "private_shadow";
