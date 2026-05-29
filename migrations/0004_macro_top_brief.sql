-- 0004_macro_top_brief.sql
-- Single-row table holding the current week's top brief as raw markdown.
-- Overwritten on every `sync_to_supabase latest` run. History is preserved in
-- git under briefs/<date>/, not in the database.

create table if not exists macro_top_brief (
  id          smallint primary key default 1 check (id = 1),  -- single-row lock
  brief_date  date not null,        -- the brief's own date, e.g. 2026-05-27
  body_md     text not null,        -- raw markdown from briefs/<date>/top.md
  updated_at  timestamptz default now()
);

drop trigger if exists macro_top_brief_set_updated_at on macro_top_brief;
create trigger macro_top_brief_set_updated_at
before update on macro_top_brief
for each row execute function set_updated_at();

alter table macro_top_brief enable row level security;

drop policy if exists "anon read" on macro_top_brief;
create policy "anon read" on macro_top_brief
  for select to anon using (true);

insert into macro_meta (key, value)
values ('schema_version', '4')
on conflict (key) do update set value = excluded.value, updated_at = now();
