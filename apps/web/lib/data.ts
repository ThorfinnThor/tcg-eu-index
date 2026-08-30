import { readAssetText } from "@runtime-data";
import { fixtureConstituents, fixtureIndexes } from "./fixtures";
import { deriveRebalanceHistory } from "./constituents";
import { applyPublicIndexMetadata, applyPublicSearchMetadata, canonicalIndexCode, indexAssetCandidates } from "./index-codes";
import type { ArchiveHealthPayload, CardImageCoveragePayload, CollectorIndexCode, CollectorIndexSummary, Constituent, DailyIndexValue, DataQualityPayload, IndexCode, IndexSummary, ReadinessPayload, RebalanceHistory, ReportsPayload, WeeklyReport } from "./types";

export const revalidate = 3600;

type SearchRecord = {
  id: IndexCode;
  slug: string;
  name: string;
  score: number | null;
  category: string;
  filterValues: {
    game: string;
    universe: "singles" | "sealed";
    status: "accumulating" | "preview" | "published";
    target_size: number;
    breadth: number;
  };
};

type StatusPayload = {
  dataset_version?: string;
  generated_at?: string | null;
  source?: string;
  last_snapshot_date: string | null;
  last_calc_date: string | null;
  gap_count: number;
  indexes: Array<{ code: string; freshness: string | null; status: string }>;
};

type ManifestPayload = {
  datasetVersion: string;
  generatedAt: string;
  schemaVersion: number;
  sourceVersions: { methodology: string; source: string };
  files: Array<{ path: string; checksum: string; bytes: number }>;
};

export function codes(): IndexCode[] {
  return [
    "MTEU500",
    "MTEUSLD",
    "YGEU500",
    "YGEUSLD",
    "OPEU500",
    "OPEUSLD",
    "PKEU500",
    "PKEUSLD",
    "DBSEU500",
    "DBSEUSLD",
    "FABEU500",
    "FABEUSLD",
    "DGEU500",
    "DGEUSLD",
    "LCEU500",
    "LCEUSLD",
    "SWUEU500",
    "SWUEUSLD",
    "RBEU500",
    "RBEUSLD"
  ];
}

async function readJson<T>(relativePath: string): Promise<T> {
  const body = await readAssetText(`data/${relativePath}`);
  return JSON.parse(body) as T;
}

function pctChange(history: DailyIndexValue[], days: number) {
  if (history.length < 2) return 0;
  const last = history[history.length - 1].index_value;
  const previous = history[Math.max(0, history.length - 1 - days)].index_value;
  return last / previous - 1;
}

export function postInceptionHistory(index: IndexSummary) {
  return index.history.filter((row) => row.value_date >= index.base_date);
}

export function changes(index: IndexSummary) {
  const history = postInceptionHistory(index);
  return {
    d1: pctChange(history, 1),
    d7: pctChange(history, 7),
    d30: pctChange(history, 30)
  };
}

function fixtureByCode(code: string) {
  const candidates = indexAssetCandidates(code);
  const fixture = fixtureIndexes.find((item) => candidates.includes(item.code));
  return fixture ? applyPublicIndexMetadata(fixture) : null;
}

async function readCodeJson<T>(code: string, fileName: string): Promise<{ payload: T; assetCode: string }> {
  let lastError: unknown;
  for (const assetCode of indexAssetCandidates(code)) {
    try {
      return { payload: await readJson<T>(`indexes/${assetCode}/${fileName}`), assetCode };
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

export async function getSearchIndex(): Promise<SearchRecord[]> {
  try {
    return (await readJson<SearchRecord[]>("search/indexes.json")).map(applyPublicSearchMetadata);
  } catch {
    return fixtureIndexes.map((index) => applyPublicSearchMetadata({
      id: index.code,
      slug: index.slug,
      name: index.name,
      score: index.history.at(-1)?.index_value ?? null,
      category: index.universe,
      filterValues: {
        game: index.game,
        universe: index.universe,
        status: index.status,
        target_size: index.target_size,
        breadth: index.breadth
      }
    }));
  }
}

export async function getIndexes(): Promise<IndexSummary[]> {
  const search = await getSearchIndex();
  const indexes = await Promise.all(search.map((record) => getIndex(record.id)));
  return indexes.filter((index): index is IndexSummary => index !== null);
}

export async function getIndex(code: string): Promise<IndexSummary | null> {
  const fixture = fixtureByCode(code);
  try {
    const summaryResult = await readCodeJson<Omit<IndexSummary, "history">>(code, "summary.json");
    const [history, previewHistory] = await Promise.all([
      readJson<DailyIndexValue[]>(`indexes/${summaryResult.assetCode}/history.json`),
      readJson<DailyIndexValue[]>(`indexes/${summaryResult.assetCode}/preview-history.json`).catch(() => [])
    ]);
    return applyPublicIndexMetadata({ ...summaryResult.payload, history, preview_history: previewHistory });
  } catch {
    return fixture;
  }
}

export async function getConstituents(code: string): Promise<Constituent[]> {
  try {
    return (await readCodeJson<Constituent[]>(code, "constituents.json")).payload;
  } catch {
    return indexAssetCandidates(code).flatMap((candidate) => fixtureConstituents[candidate] ?? []);
  }
}

export async function getRebalanceHistory(code: IndexCode): Promise<RebalanceHistory> {
  try {
    const payload = (await readCodeJson<RebalanceHistory>(code, "rebalances.json")).payload;
    return { ...payload, index_code: canonicalIndexCode(payload.index_code) as IndexCode };
  } catch {
    const [index, constituents] = await Promise.all([getIndex(code), getConstituents(code)]);
    const generatedFor = latestDate(constituents, index?.base_date ?? "1970-01-01");
    return deriveRebalanceHistory(
      code,
      constituents,
      index?.history_start_kind === "published"
        ? "published"
        : index?.history_start_kind === "preview"
          ? "preview"
          : "validation",
      generatedFor
    );
  }
}

function latestDate(constituents: Constituent[], fallback: string) {
  return constituents.reduce((latest, item) => {
    const candidate = item.removed_at && item.removed_at > item.member_since ? item.removed_at : item.member_since;
    return candidate > latest ? candidate : latest;
  }, fallback);
}

export async function getStatus(): Promise<StatusPayload> {
  try {
    const status = await readJson<StatusPayload>("status/latest.json");
    return {
      ...status,
      indexes: status.indexes.map((index) => ({ ...index, code: canonicalIndexCode(index.code) }))
    };
  } catch {
    const indexes = await getIndexes();
    const latestDates = indexes.map((index) => index.history.at(-1)?.value_date).filter(Boolean);
    return {
      dataset_version: "fixture-fallback",
      generated_at: null,
      source: "packaged-fixtures",
      last_snapshot_date: latestDates.sort().at(-1) ?? null,
      last_calc_date: latestDates.sort().at(-1) ?? null,
      gap_count: 0,
      indexes: indexes.map((index) => ({
        code: index.code,
        freshness: index.history.at(-1)?.value_date ?? null,
        status: index.status
      }))
    };
  }
}

export async function getManifest(): Promise<ManifestPayload | null> {
  try {
    return await readJson<ManifestPayload>("manifest.json");
  } catch {
    return null;
  }
}

export async function getDataQuality(): Promise<DataQualityPayload> {
  try {
    return await readJson<DataQualityPayload>("data-quality/latest.json");
  } catch {
    return {
      datasetCompleteness: 0,
      sourceCoverage: "fallback fixtures",
      licensingPosture: "derived-aggregates-only",
      limitations: [
        {
          title: "Fallback mode",
          body: "Generated static data files were unavailable, so the app is displaying packaged fixtures."
        }
      ],
      checks: [{ id: "fallback", label: "Fallback fixture mode", status: "warn", detail: "Public data export was not found." }],
      gaps: []
    };
  }
}

export async function getArchiveHealth(): Promise<ArchiveHealthPayload> {
  try {
    return await readJson<ArchiveHealthPayload>("archive-health/latest.json");
  } catch {
    return {
      schemaVersion: 1,
      generatedFor: null,
      status: "pending_first_audit",
      since: null,
      until: null,
      expectedDays: null,
      manifestCount: null,
      coverageRatio: null,
      verifiedFileCount: null,
      integrityErrorCount: null,
      warningCount: null,
      gapCount: null,
      gaps: [],
      storage: { bytes: null, freeTierBytes: 10_000_000_000, usageRatio: null, status: "pending" },
      operations: {
        billingMonth: null,
        classA: { projected: null, freeTier: 1_000_000, usageRatio: null, status: "pending" },
        classB: { projected: null, freeTier: 10_000_000, usageRatio: null, status: "pending" }
      },
      cutoverProjection: {
        firstFullObservationDate: null,
        firstEligibleEffectiveDate: null,
        firstMonthlyRebalanceDate: null,
        assumesNoGaps: true
      }
    };
  }
}

export async function getCardImageCoverage(): Promise<CardImageCoveragePayload> {
  try {
    const index = await readJson<{
      generated_for: string;
      indexes: Array<{ code: CollectorIndexCode; name: string; game_key: string }>;
    }>("collector/index.json");
    const rows = await Promise.all(index.indexes.map(async (item) => {
      const summary = await readJson<CollectorIndexSummary>(`collector/${item.code}/summary.json`);
      const counts = summary.product_metadata.image_status_counts ?? {};
      const count = (status: string) => counts[status] ?? 0;
      const identifiedRows = count("exact") + count("manual") + count("blocked_legal");
      const missingRows = count("missing_prerequisite") + count("provider_missing")
        + count("provider_error") + count("disabled");
      return {
        code: item.code,
        name: item.name,
        gameKey: item.game_key,
        totalRows: summary.product_metadata.constituent_count,
        identifiedRows,
        publishedRows: count("exact") + count("manual"),
        blockedLegalRows: count("blocked_legal"),
        blockedCredentialRows: count("blocked_credentials"),
        ambiguousRows: count("ambiguous") + count("probable"),
        missingRows,
        identifiedRatio: summary.product_metadata.constituent_count
          ? identifiedRows / summary.product_metadata.constituent_count
          : 0
      };
    }));
    return { generatedFor: index.generated_for, rows };
  } catch {
    return { generatedFor: null, rows: [] };
  }
}

export async function getReadiness(): Promise<ReadinessPayload> {
  try {
    const readiness = await readJson<ReadinessPayload>("readiness/latest.json");
    return {
      ...readiness,
      indexes: readiness.indexes.map((index) => ({
        ...index,
        code: canonicalIndexCode(index.code) as IndexCode
      }))
    };
  } catch {
    return {
      schemaVersion: 1,
      generatedFor: null,
      methodologyVersion: "unknown",
      state: "collecting",
      publicationStatus: "blocked_until_human_cutover",
      humanReviewRequired: true,
      source: "fallback",
      indexes: []
    };
  }
}

export async function getReports(): Promise<ReportsPayload> {
  try {
    return await readJson<ReportsPayload>("reports/index.json");
  } catch {
    return {
      newsletterProvider: "disabled",
      signupEnabled: false,
      reports: []
    };
  }
}

export async function getReport(week: string): Promise<WeeklyReport | null> {
  const payload = await getReports();
  return payload.reports.find((report) => report.week === week) ?? null;
}
