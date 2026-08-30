export type IndexCode =
  | "MTEU500"
  | "MTEUSLD"
  | "YGEU500"
  | "YGEUSLD"
  | "OPEU500"
  | "OPEUSLD"
  | "PKEU500"
  | "PKEUSLD"
  | "DBSEU500"
  | "DBSEUSLD"
  | "FABEU500"
  | "FABEUSLD"
  | "DGEU500"
  | "DGEUSLD"
  | "LCEU500"
  | "LCEUSLD"
  | "SWUEU500"
  | "SWUEUSLD"
  | "RBEU500"
  | "RBEUSLD";

export type CollectorIndexCode =
  | "MTEUCOL"
  | "MTEUSCOL"
  | "YGEUCOL"
  | "YGEUSCOL"
  | "OPEUCOL"
  | "OPEUSCOL"
  | "PKEUCOL"
  | "PKEUSCOL"
  | "DBSEUCOL"
  | "DBSEUSCOL"
  | "FABEUCOL"
  | "FABEUSCOL"
  | "DGEUCOL"
  | "DGEUSCOL"
  | "LCEUCOL"
  | "LCEUSCOL"
  | "SWUEUCOL"
  | "SWUEUSCOL"
  | "RBEUCOL"
  | "RBEUSCOL";

export type CollectorDataState = "private_shadow";

export type CollectorPriceState =
  | "initialized"
  | "fresh"
  | "fresh_after_carry"
  | "fresh_after_suspension"
  | "spike_capped"
  | "carried_forward"
  | "suspended_stale"
  | "snapshot_unchanged";

export type CardImageStatus =
  | "exact"
  | "manual"
  | "probable"
  | "ambiguous"
  | "missing_prerequisite"
  | "provider_missing"
  | "provider_error"
  | "blocked_legal"
  | "blocked_credentials"
  | "disabled";

export type CardImageVariant = {
  url: string;
  width: number | null;
  height: number | null;
  mime_type: string | null;
  storage_mode: "remote" | "r2";
  r2_key: string | null;
  content_sha256: string | null;
};

export type CardImageFace = {
  face: "front" | "back" | "other";
  thumb: CardImageVariant | null;
  normal: CardImageVariant | null;
  large: CardImageVariant | null;
};

export type PublicCardImage = {
  status: CardImageStatus;
  provider?: string | null;
  match_method?: string;
  language?: string | null;
  language_match?: "exact" | "fallback" | "unknown" | null;
  artwork_variant?: string | null;
  front?: CardImageFace | null;
  back?: CardImageFace | null;
  verified_at?: string | null;
};

export type CollectorDailyIndexValue = {
  value_date: string;
  index_value: number | null;
  daily_return: number | null;
  status: "active" | "empty_eligible_universe";
  constituent_count: number;
  fresh_count: number;
  capped_count: number;
  carried_count: number;
  suspended_count: number;
  capped_weight_share: number;
  carried_weight_share: number;
  suspended_weight_share: number;
  largest_end_weight: number;
  whole_market_carried_forward: boolean;
  rebalance_effective_date: string;
  selection_as_of: string;
  methodology_version: string;
};

export type CollectorContribution = {
  value_date: string;
  stable_variant_id: string;
  cm_product_id: number;
  variant_key: string;
  target_weight: number | null;
  weight_before: number;
  raw_return: number | null;
  used_return: number;
  contribution: number;
  weight_after: number;
  valuation_price: number | null;
  price_state: CollectorPriceState;
  capped: boolean;
};

export type CollectorRebalanceRecord = {
  effective_date: string;
  selection_as_of: string;
  methodology_version: string;
  selection_snapshot_sha256: string;
  eligible_count: number;
  active_count: number;
  constituents: Array<{
    cm_product_id: number;
    variant_key: string;
    stable_variant_id: string;
    selection_price: number;
    name: string;
    set_name: string | null;
    collector_number: string | null;
    cm_expansion_id: number | null;
    image_url: string | null;
    image_source: string | null;
    image?: PublicCardImage;
    tcgplayer_product_url: string | null;
    metadata_status: string;
  }>;
};

export type CollectorEligibilityDiagnostic = {
  cm_product_id: number;
  variant_key: string;
  stable_variant_id: string;
  eligible: boolean;
  exclusion_reasons: string[];
  reference_price: number | null;
  history_days: number;
  valuation_observation_ratio: number;
  selection_price_observation_ratio: number;
  suspect_zero_ratio: number;
  price_update_frequency: number;
  inverse_dispersion: number;
  data_quality_score: number;
  activity_days: number;
  activity_ratio: number;
  observable_activity_days: number;
  last_positive_avg1_date: string | null;
  days_since_positive_avg1: number | null;
  repeated_positive_avg1_days: number;
};

export type CollectorOutputManifest = {
  schema_version: 2;
  series_id: string;
  index_code: CollectorIndexCode;
  methodology_version: string;
  data_state: CollectorDataState;
  public_alias_enabled: false;
  generated_for: string;
  engine_revision: string;
  source_hashes: Record<string, string>;
  outputs: Record<string, { key: string; sha256: string; bytes: number }>;
};

export type CollectorIndexSummary = {
  schema_version: 2;
  series_id: string;
  index_code: CollectorIndexCode;
  methodology_version: string;
  data_state: CollectorDataState;
  public_alias_enabled: false;
  name: string;
  game_key: string;
  universe: "singles" | "sealed";
  target_size: null;
  base_value: number;
  status: "accumulating" | "preview";
  history_start_date: string | null;
  latest_value_date: string | null;
  latest_index_value: number | null;
  latest_rebalance: string | null;
  product_metadata: {
    constituent_count: number;
    named_count: number;
    set_name_count: number;
    collector_number_count: number;
    image_count: number;
    image_status_counts?: Record<string, number>;
  };
  generated_for: string;
};

export type CollectorHistory = {
  schema_version: 2;
  series_id: string;
  index_code: CollectorIndexCode;
  methodology_version: string;
  data_state: CollectorDataState;
  generated_for: string;
  records: CollectorDailyIndexValue[];
};

export type CollectorRebalances = {
  schema_version: 2;
  series_id: string;
  index_code: CollectorIndexCode;
  methodology_version: string;
  data_state: CollectorDataState;
  cadence: "monthly";
  generated_for: string;
  rebalances: CollectorRebalanceRecord[];
};

export type CollectorCompositionIndex = {
  schema_version: 2;
  series_id: string;
  index_code: CollectorIndexCode;
  methodology_version: string;
  data_state: CollectorDataState;
  publication_state: "preview_noindex";
  generated_for: string;
  rebalances: Array<{
    effective_date: string;
    selection_as_of: string;
    active_count: number;
    page_size: number;
    page_count: number;
    pages: Array<{
      page: number;
      path: string;
      sha256: string;
      bytes: number;
    }>;
  }>;
};

export type CollectorCompositionPage = {
  schema_version: 2;
  series_id: string;
  index_code: CollectorIndexCode;
  methodology_version: string;
  data_state: CollectorDataState;
  publication_state: "preview_noindex";
  generated_for: string;
  effective_date: string;
  page: number;
  page_count: number;
  constituents: CollectorRebalanceRecord["constituents"];
};

export type CollectorDiagnostics = {
  schema_version: 2;
  series_id: string;
  index_code: CollectorIndexCode;
  methodology_version: string;
  data_state: CollectorDataState;
  generated_for: string;
  daily: CollectorDailyIndexValue[];
  eligibility: CollectorEligibilityDiagnostic[];
  summary?: {
    count: number;
    average_quality: number | null;
    average_activity_ratio: number | null;
    positive_activity_rows: number;
  };
};

export type CollectorPreviewIndex = {
  code: CollectorIndexCode;
  name: string;
  game_key: string;
  status: "accumulating" | "preview";
  base_value: number;
  latest_index_value: number | null;
  latest_value_date: string | null;
  constituent_count: number;
};

export type CollectorPreviewIndexPayload = {
  schema_version: 1;
  publication_state: "preview_noindex";
  generated_for: string;
  methodology_version: string;
  indexes: CollectorPreviewIndex[];
};

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
  history_start_kind: "validation" | "preview" | "published";
  base_date: string;
  official_base_date?: string;
  status: "accumulating" | "preview" | "published";
  target_size: number;
  breadth: number;
  volatility_30d: number;
  history: DailyIndexValue[];
  preview_history?: DailyIndexValue[];
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
  data_state: "validation" | "preview" | "published";
  cadence: "monthly" | "daily_preview";
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

export type ArchiveHealthPayload = {
  schemaVersion: 1;
  generatedFor: string | null;
  status: "pending_first_audit" | "healthy" | "attention_required";
  since: string | null;
  until: string | null;
  expectedDays: number | null;
  manifestCount: number | null;
  coverageRatio: number | null;
  verifiedFileCount: number | null;
  integrityErrorCount: number | null;
  warningCount: number | null;
  gapCount: number | null;
  gaps: Array<{ date: string; game: string | null; reason: string }>;
  storage: {
    bytes: number | null;
    freeTierBytes: number;
    usageRatio: number | null;
    status: string;
  };
  operations: {
    billingMonth: string | null;
    classA: OperationBudget;
    classB: OperationBudget;
  };
  cutoverProjection: {
    firstFullObservationDate: string | null;
    firstEligibleEffectiveDate: string | null;
    firstMonthlyRebalanceDate: string | null;
    assumesNoGaps: boolean;
  };
};

type OperationBudget = {
  projected: number | null;
  freeTier: number;
  usageRatio: number | null;
  status: string;
};

export type IndexReadiness = {
  code: IndexCode;
  state: "pending_receipt" | "accumulating" | "eligible_for_human_review";
  availableArchiveDays: number | null;
  requiredLookbackDays: number;
  daysRemaining: number | null;
  selectedConstituents: number | null;
  targetSize: number;
  languageScope: "all-cardmarket-europe-languages";
  gates: Record<string, boolean>;
  blockers: string[];
};

export type ReadinessPayload = {
  schemaVersion: 1;
  generatedFor: string | null;
  methodologyVersion: string;
  state: "collecting" | "eligible_for_human_review";
  publicationStatus: "blocked_until_human_cutover";
  humanReviewRequired: true;
  source: string;
  indexes: IndexReadiness[];
};

export type ReportHighlight = {
  code: IndexCode;
  chartPath?: string;
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
