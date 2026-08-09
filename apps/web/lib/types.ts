export type IndexCode = "OPEU100" | "PKEU250" | "OPEUSLD";

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
  liquidity_score: number;
  ref_price: number;
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
