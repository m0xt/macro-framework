-- 0003_macro_stress_score.sql
-- Add continuous 0-10 macro stress visualization fields alongside the existing
-- MRMI stress_intensity buffer gate.

alter table macro_snapshots
  add column stress_score numeric,
  add column stress_growth_pressure numeric,
  add column stress_inflation_pressure numeric,
  add column stress_score_bucket text check (stress_score_bucket in ('calm','watch','building','elevated'));

insert into macro_meta (key, value)
values ('schema_version', '3')
on conflict (key) do update set value = excluded.value, updated_at = now();
