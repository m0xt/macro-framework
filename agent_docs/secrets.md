# Secrets

`macro-framework` only needs secrets for Supabase sync. Yahoo/FRED data fetches use public endpoints, and weekly briefs use the logged-in `claude` CLI subscription rather than an Anthropic API key.

## Required secrets

| Name | Required for | Notes |
|---|---|---|
| `SUPABASE_URL` | `sync_to_supabase.py doctor/latest/backfill` | Project URL, e.g. `https://<ref>.supabase.co`. |
| `SUPABASE_SERVICE_KEY` | Supabase writes/backfills | Service-role key. Treat as sensitive; never expose to browser bundles or commit. |

## Location

Target skeleton location:

```text
~/ops/secrets/macro-framework/.env
```

Current state:

- `sync_to_supabase.py` calls `load_dotenv()` and therefore reads project-root `.env` plus process environment.
- `.env.example` is committed as the template.
- Real `.env` is ignored and must not be committed.
- Migration to `~/ops/secrets/macro-framework/.env` under git-crypt is pending; do not move live secrets unless that dispatch explicitly asks for it.

Expected `.env` shape:

```dotenv
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_KEY=...
```

## Missing or bad secrets

If env vars are missing, `sync_to_supabase.py` exits with code `20` and prints `error[supabase-auth]`.

Manual check:

```bash
cd ~/projects/macro-framework
uv run python sync_to_supabase.py doctor
```

`scripts/refresh.sh` treats Supabase auth failures as sync-only failures after a successful local dashboard build: local dashboard/snapshot outputs can still commit, and status will say `refresh ok, supabase sync failed (supabase-auth)`.

## Rotation runbook

1. Create or rotate the Supabase service-role key in the Supabase dashboard.
2. Update the active secret store:
   - current: project-root `.env` on the Mac mini, or launchd/process environment
   - future: `~/ops/secrets/macro-framework/.env`
3. Do not paste the key into docs, tickets, commits, shell history snippets, or chat.
4. Run:
   ```bash
   cd ~/projects/macro-framework
   uv run python sync_to_supabase.py doctor
   uv run python sync_to_supabase.py latest
   ```
5. If `doctor` fails with schema drift after rotation, the key is probably valid but the remote schema still needs `supabase_schema.sql` applied.
6. If `doctor` fails with auth, verify the key type and project URL match.

## Applying the future ops-secret migration

When the dedicated migration happens:

1. Create `~/ops/secrets/macro-framework/.env` under the encrypted ops-secret workflow.
2. Move the real values there.
3. Update `sync_to_supabase.py` or the launchd environment so the file is loaded explicitly.
4. Keep `.env.example` in this repo.
5. Run tests plus Supabase doctor/latest.
6. Document the change in `DECISIONS.md`.
