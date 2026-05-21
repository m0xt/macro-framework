-- 0002_macro_meta.sql
-- macro_meta sentinel table: tracks schema_version so sync_to_supabase doctor
-- can detect drift between local code and the remote schema.
--
-- Bump procedure when adding a new migration that changes shape:
--   1. Add migrations/000N_<change>.sql with the DDL.
--   2. In that same migration, update the macro_meta schema_version sentinel
--      to N (matching the new highest migration number).
--   3. Update EXPECTED_SCHEMA_VERSION in src/macro_framework/sync_to_supabase.py.

create table if not exists macro_meta (
  key        text primary key,
  value      text not null,
  updated_at timestamptz default now()
);

insert into macro_meta (key, value)
values ('schema_version', '1')
on conflict (key) do update set value = excluded.value, updated_at = now();

alter table macro_meta enable row level security;

drop policy if exists "anon read" on macro_meta;
create policy "anon read" on macro_meta
  for select to anon using (true);
