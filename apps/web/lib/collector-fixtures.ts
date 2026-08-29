import type {
  CollectorDiagnostics,
  CollectorHistory,
  CollectorIndexSummary,
  CollectorRebalances
} from "./types";

export const collectorFixtureSummary: CollectorIndexSummary = {
  schema_version: 2,
  series_id: "OPEUCOL:1.5.0-preview.1:private_shadow",
  index_code: "OPEUCOL",
  methodology_version: "1.5.0-preview.1",
  data_state: "private_shadow",
  public_alias_enabled: false,
  name: "One Piece Europe Collector Index",
  game_key: "onepiece",
  universe: "singles",
  target_size: null,
  base_value: 1000,
  status: "preview",
  history_start_date: "2026-08-20",
  latest_value_date: "2026-08-21",
  latest_index_value: 1005,
  latest_rebalance: "2026-08-20",
  generated_for: "2026-08-21"
};

export const collectorFixtureHistory: CollectorHistory = {
  schema_version: 2,
  series_id: collectorFixtureSummary.series_id,
  index_code: collectorFixtureSummary.index_code,
  methodology_version: collectorFixtureSummary.methodology_version,
  data_state: "private_shadow",
  generated_for: "2026-08-21",
  records: [
    {
      value_date: "2026-08-20",
      index_value: 1000,
      daily_return: 0,
      status: "active",
      constituent_count: 2,
      fresh_count: 2,
      capped_count: 0,
      carried_count: 0,
      suspended_count: 0,
      capped_weight_share: 0,
      carried_weight_share: 0,
      suspended_weight_share: 0,
      largest_end_weight: 0.5,
      whole_market_carried_forward: false,
      rebalance_effective_date: "2026-08-20",
      selection_as_of: "2026-08-19",
      methodology_version: "1.5.0-preview.1"
    },
    {
      value_date: "2026-08-21",
      index_value: 1005,
      daily_return: 0.005,
      status: "active",
      constituent_count: 2,
      fresh_count: 2,
      capped_count: 0,
      carried_count: 0,
      suspended_count: 0,
      capped_weight_share: 0,
      carried_weight_share: 0,
      suspended_weight_share: 0,
      largest_end_weight: 0.5025,
      whole_market_carried_forward: false,
      rebalance_effective_date: "2026-08-20",
      selection_as_of: "2026-08-19",
      methodology_version: "1.5.0-preview.1"
    }
  ]
};

export const collectorFixtureRebalances: CollectorRebalances = {
  schema_version: 2,
  series_id: collectorFixtureSummary.series_id,
  index_code: collectorFixtureSummary.index_code,
  methodology_version: collectorFixtureSummary.methodology_version,
  data_state: "private_shadow",
  cadence: "monthly",
  generated_for: "2026-08-21",
  rebalances: [
    {
      effective_date: "2026-08-20",
      selection_as_of: "2026-08-19",
      methodology_version: "1.5.0-preview.1",
      selection_snapshot_sha256: "a".repeat(64),
      eligible_count: 2,
      active_count: 2,
      constituents: [
        { cm_product_id: 1, variant_key: "foil", stable_variant_id: "cardmarket:onepiece:product:1:foil", selection_price: 20 },
        { cm_product_id: 1, variant_key: "nonfoil", stable_variant_id: "cardmarket:onepiece:product:1:nonfoil", selection_price: 10 }
      ]
    }
  ]
};

export const collectorFixtureDiagnostics: CollectorDiagnostics = {
  schema_version: 2,
  series_id: collectorFixtureSummary.series_id,
  index_code: collectorFixtureSummary.index_code,
  methodology_version: collectorFixtureSummary.methodology_version,
  data_state: "private_shadow",
  generated_for: "2026-08-21",
  daily: collectorFixtureHistory.records,
  eligibility: []
};
