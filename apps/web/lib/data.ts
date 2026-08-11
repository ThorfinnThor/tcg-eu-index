import { readFile } from "node:fs/promises";
import path from "node:path";
import { fixtureConstituents, fixtureIndexes } from "./fixtures";
import { deriveRebalanceHistory } from "./constituents";
import type { Constituent, DailyIndexValue, DataQualityPayload, IndexCode, IndexSummary, RebalanceHistory, ReportsPayload, WeeklyReport } from "./types";

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
    status: "accumulating" | "published";
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

const dataRoot = path.join(process.cwd(), "public", "data");

export function codes(): IndexCode[] {
  return [
    "MTEU500",
    "YGEU250",
    "OPEU100",
    "PKEU250",
    "OPEUSLD",
    "DBSEU100",
    "FABEU100",
    "DGEU100",
    "LCEU100",
    "SWUEU100",
    "RBEU100"
  ];
}

async function readJson<T>(relativePath: string): Promise<T> {
  const body = await readFile(path.join(dataRoot, relativePath), "utf8");
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
  return fixtureIndexes.find((item) => item.code === code) ?? null;
}

export async function getSearchIndex(): Promise<SearchRecord[]> {
  try {
    return await readJson<SearchRecord[]>("search/indexes.json");
  } catch {
    return fixtureIndexes.map((index) => ({
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
    const [summary, history] = await Promise.all([
      readJson<Omit<IndexSummary, "history">>(`indexes/${code}/summary.json`),
      readJson<DailyIndexValue[]>(`indexes/${code}/history.json`)
    ]);
    return { ...summary, history };
  } catch {
    return fixture;
  }
}

export async function getConstituents(code: string): Promise<Constituent[]> {
  try {
    return await readJson<Constituent[]>(`indexes/${code}/constituents.json`);
  } catch {
    return fixtureConstituents[code] ?? [];
  }
}

export async function getRebalanceHistory(code: IndexCode): Promise<RebalanceHistory> {
  try {
    return await readJson<RebalanceHistory>(`indexes/${code}/rebalances.json`);
  } catch {
    const [index, constituents] = await Promise.all([getIndex(code), getConstituents(code)]);
    const generatedFor = latestDate(constituents, index?.base_date ?? "1970-01-01");
    return deriveRebalanceHistory(
      code,
      constituents,
      index?.history_start_kind === "published" ? "published" : "validation",
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
    return await readJson<StatusPayload>("status/latest.json");
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
