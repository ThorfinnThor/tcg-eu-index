create extension if not exists pgcrypto;

create table games (
  id bigint generated always as identity primary key,
  cm_game_key text not null unique,
  name text not null
);

create table sets (
  id bigint generated always as identity primary key,
  game_id bigint not null references games(id),
  cm_expansion_id integer not null,
  name text not null,
  release_date date,
  unique(game_id, cm_expansion_id)
);

create table products (
  id bigint generated always as identity primary key,
  game_id bigint not null references games(id),
  set_id bigint references sets(id),
  cm_product_id bigint not null unique,
  name text not null,
  product_kind text not null check (product_kind in ('single','sealed','other')),
  raw_category text,
  first_seen date not null,
  last_seen date not null
);

create table variants (
  id bigint generated always as identity primary key,
  product_id bigint not null references products(id),
  variant_key text not null,
  unique(product_id, variant_key)
);

create table archive_gaps (
  value_date date not null,
  game_id bigint not null references games(id),
  reason text not null,
  detected_at timestamptz not null default now(),
  primary key (value_date, game_id)
);

create table ingest_runs (
  id bigint generated always as identity primary key,
  run_date date not null,
  game_id bigint not null references games(id),
  status text not null,
  notes text,
  snapshot_sha text not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  unique(run_date, game_id)
);

create table index_definitions (
  id bigint generated always as identity primary key,
  code text not null unique,
  name text not null,
  game_id bigint not null references games(id),
  universe text not null check (universe in ('singles','sealed')),
  target_size integer not null,
  methodology_version text not null,
  filter_json jsonb not null default '{}'::jsonb,
  base_date date not null,
  base_value numeric not null default 1000,
  status text not null check (status in ('draft','accumulating','published','retired'))
);

create table index_rebalances (
  id bigint generated always as identity primary key,
  index_id bigint not null references index_definitions(id),
  effective_date date not null,
  methodology_version text not null,
  selection_snapshot_sha text not null,
  notes text,
  unique(index_id, effective_date)
);

create table index_constituents (
  id bigint generated always as identity primary key,
  rebalance_id bigint not null references index_rebalances(id),
  variant_id bigint not null references variants(id),
  action text not null check (action in ('added','retained','removed')),
  reason text not null,
  liquidity_score numeric,
  ref_price numeric
);

create table daily_index_values (
  id bigint generated always as identity primary key,
  index_id bigint not null references index_definitions(id),
  value_date date not null,
  index_value numeric(16,6) not null,
  daily_return numeric(12,8) not null,
  n_constituents_active integer not null,
  n_capped integer not null,
  n_carried_forward integer not null,
  calc_version text not null,
  unique(index_id, value_date, calc_version)
);

create table index_contributions (
  id bigint generated always as identity primary key,
  index_id bigint not null references index_definitions(id),
  value_date date not null,
  variant_id bigint not null references variants(id),
  weight numeric(12,8) not null,
  used_return numeric(12,8) not null,
  contribution numeric(12,8) not null
);

create table index_analytics (
  index_id bigint not null references index_definitions(id),
  value_date date not null,
  window text not null,
  movers_json jsonb not null,
  breadth numeric,
  volatility_30d numeric,
  drawdown numeric,
  primary key(index_id, value_date, window)
);

create table portfolios (
  id bigint generated always as identity primary key,
  public_token text not null unique default encode(gen_random_bytes(18), 'hex'),
  name text not null,
  created_at timestamptz not null default now()
);

create table portfolio_holdings (
  id bigint generated always as identity primary key,
  portfolio_id bigint not null references portfolios(id),
  variant_id bigint not null references variants(id),
  quantity numeric not null,
  cost_basis numeric
);

create table portfolio_daily_values (
  portfolio_id bigint not null references portfolios(id),
  value_date date not null,
  value numeric(14,2) not null,
  primary key(portfolio_id, value_date)
);

create or replace function prevent_append_only_mutation()
returns trigger
language plpgsql
as $$
begin
  raise exception 'append-only table % cannot be updated or deleted', tg_table_name;
end;
$$;

create trigger daily_index_values_append_only
before update or delete on daily_index_values
for each row execute function prevent_append_only_mutation();

create trigger index_rebalances_append_only
before update or delete on index_rebalances
for each row execute function prevent_append_only_mutation();

create trigger index_constituents_append_only
before update or delete on index_constituents
for each row execute function prevent_append_only_mutation();

create view v_daily_index_values_current as
select distinct on (index_id, value_date)
  *
from daily_index_values
order by index_id, value_date, calc_version desc;
