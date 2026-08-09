alter table games enable row level security;
alter table sets enable row level security;
alter table products enable row level security;
alter table variants enable row level security;
alter table archive_gaps enable row level security;
alter table ingest_runs enable row level security;
alter table index_definitions enable row level security;
alter table index_rebalances enable row level security;
alter table index_constituents enable row level security;
alter table daily_index_values enable row level security;
alter table index_contributions enable row level security;
alter table index_analytics enable row level security;
alter table portfolios enable row level security;
alter table portfolio_holdings enable row level security;
alter table portfolio_daily_values enable row level security;

create policy public_read_games on games for select to anon using (true);
create policy public_read_sets on sets for select to anon using (true);
create policy public_read_products on products for select to anon using (true);
create policy public_read_variants on variants for select to anon using (true);
create policy public_read_archive_gaps on archive_gaps for select to anon using (true);

create policy public_read_index_definitions on index_definitions
for select to anon using (status in ('published', 'accumulating'));

create policy public_read_index_rebalances on index_rebalances
for select to anon using (
  exists (
    select 1 from index_definitions d
    where d.id = index_rebalances.index_id
      and d.status in ('published', 'accumulating')
  )
);

create policy public_read_index_constituents on index_constituents
for select to anon using (
  exists (
    select 1
    from index_rebalances r
    join index_definitions d on d.id = r.index_id
    where r.id = index_constituents.rebalance_id
      and d.status in ('published', 'accumulating')
  )
);

create policy public_read_daily_index_values on daily_index_values
for select to anon using (
  exists (
    select 1 from index_definitions d
    where d.id = daily_index_values.index_id
      and d.status in ('published', 'accumulating')
  )
);

create policy public_read_index_analytics on index_analytics
for select to anon using (
  exists (
    select 1 from index_definitions d
    where d.id = index_analytics.index_id
      and d.status in ('published', 'accumulating')
  )
);
