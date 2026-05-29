-- 0005_macro_backtest.sql
-- Single-row table holding the dashboard backtest stats as a JSON blob.
-- Overwritten on every `sync_to_supabase latest` run. Source of truth is the
-- static BACKTEST_STATS constant in build.py (Task 35 research figures).

create table if not exists macro_backtest (
  id          smallint primary key default 1 check (id = 1),  -- single-row lock
  stats       jsonb not null,
  updated_at  timestamptz default now()
);

drop trigger if exists macro_backtest_set_updated_at on macro_backtest;
create trigger macro_backtest_set_updated_at
before update on macro_backtest
for each row execute function set_updated_at();

alter table macro_backtest enable row level security;

drop policy if exists "anon read" on macro_backtest;
create policy "anon read" on macro_backtest
  for select to anon using (true);

insert into macro_meta (key, value)
values ('schema_version', '5')
on conflict (key) do update set value = excluded.value, updated_at = now();
