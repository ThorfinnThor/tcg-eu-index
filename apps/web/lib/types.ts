export type IndexCode =
  | "MTEU500"
  | "YGEU250"
  | "OPEU100"
  | "PKEU250"
  | "OPEUSLD"
  | "DBSEU100"
  | "FABEU100"
  | "DGEU100"
  | "LCEU100"
  | "SWUEU100"
  | "RBEU100";

export type DailyIndexValue = {
  value_date: string;
  index_value: number;
  daily_return: number;
  n_constituents_active: number;
  n_capped?: number;
  n_carried_forward?: number;
  calc_version?: string;
};

export type IndexSummary = {
  code: IndexCode;
  slug: string;
  name: string;
  game: string;
  universe: "singles" | "sealed";
  history_start_date: string;
  history_start_kind: "validation" | "published";
  base_date: string;
  status: "accumulating" | "published";
  target_size: number;
  breadth: number;
  volatility_30d: number;
  history: DailyIndexValue[];
};

export type Constituent = {
  cm_product_id: number;
  variant_key: string;
  name: string;
  set: string;
  member_since: string;
  removed_at?: string | null;
  action: "added" | "retained" | "removed";
  entry_reason?: string;
  removal_reason?: string;
  liquidity_score: number;
  ref_price: number;
};

export type RebalanceChange = {
  cm_product_id: number;
  variant_key: string;
  action: "added" | "removed";
  reason: string;
};

export type RebalanceRecord = {
  effective_date: string;
  methodology_version: string;
  selection_snapshot_sha256?: string | null;
  eligible_count?: number | null;
  active_count: number;
  retained_count: number;
  changes: RebalanceChange[];
};

export type RebalanceHistory = {
  schema_version: 1;
  index_code: IndexCode;
  data_state: "validation" | "published";
  cadence: "monthly";
  generated_for: string;
  rebalances: RebalanceRecord[];
};

export type DataQualityPayload = {
  datasetCompleteness: number;
  sourceCoverage: string;
  licensingPosture: string;
  limitations: Array<{ title: string; body: string }>;
  checks: Array<{ id: string; label: string; status: "pass" | "warn" | "pending" | "fail"; detail: string }>;
  gaps: Array<{ date: string; game?: string; reason: string; detected_at?: string }>;
};

export type ReportHighlight = {
  code: IndexCode;
  headline: string;
  weeklyReturn: number;
  breadth: number;
  startValue?: number;
  endValue?: number;
  observations?: number;
  notableEvents?: string[];
};

export type WeeklyReport = {
  id: string;
  week: string;
  title: string;
  status: "draft" | "published";
  publishedAt: string | null;
  summary: string;
  notes: string[];
  indexHighlights: ReportHighlight[];
};

export type ReportsPayload = {
  newsletterProvider: string;
  signupEnabled: boolean;
  reports: WeeklyReport[];
};
