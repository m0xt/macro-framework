-- macro_snapshots: daily computed indicators from Macro Framework.
-- Apply via Supabase SQL editor or `psql`. Idempotent for fresh projects only.

create table if not exists macro_snapshots (
  date              date primary key,
  -- Headline (from snapshot.mrmi_combined.*)
  mrmi              numeric,
  mrmi_state        text check (mrmi_state in ('LONG','CASH')),
  mmi               numeric,
  stress_intensity  numeric,
  macro_buffer      numeric,
  -- Macro stress inputs (snapshot.macro.*)
  real_economy      numeric,
  inflation_dir_pp  numeric,
  core_cpi_yoy_pct  numeric,
  -- MMI components (snapshot.components.*)
  gii_fast          numeric,
  breadth           numeric,
  fincon            numeric,
  -- Full point-in-time blob; null for historical backfilled rows.
  snapshot          jsonb,
  created_at        timestamptz default now(),
  updated_at        timestamptz default now()
);

create index if not exists macro_snapshots_state_idx on macro_snapshots(mrmi_state);
create index if not exists macro_snapshots_snapshot_idx on macro_snapshots using gin (snapshot);

create or replace function set_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists macro_snapshots_set_updated_at on macro_snapshots;
create trigger macro_snapshots_set_updated_at
before update on macro_snapshots
for each row execute function set_updated_at();

-- RLS: public read, no public write.
alter table macro_snapshots enable row level security;

drop policy if exists "anon read" on macro_snapshots;
create policy "anon read" on macro_snapshots
  for select to anon using (true);
