# Supabase + Resend setup (Milestone 1)

## 1. Create the project

1. Create a project at <https://supabase.com>. Note the **Project URL**, **anon key**,
   **service_role key** and (legacy projects) the **JWT secret** from
   *Project Settings → API*.
2. Copy `.env.example` to `.env` and fill in:
   - `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
   - `SUPABASE_JWT_SECRET` (only if your project still uses HS256 JWTs)
   - `DATABASE_URL` (Project Settings → Database; use the **pooler** URI on
     port 6543 if you deploy the API serverlessly)
3. Frontend values (public, safe to expose): `VITE_SUPABASE_URL`,
   `VITE_SUPABASE_ANON_KEY`.

## 2. Apply the schema

```bash
pip install -e ".[api]"
python scripts/apply_migrations.py            # uses DATABASE_URL
```

Or paste `supabase/migrations/0001_schema.sql` then `0002_rls.sql` into the
Supabase dashboard SQL editor and run them in order.

## 3. Configure authentication

Project Settings → Authentication:

- **Site URL**: your dev origin, e.g. `http://localhost:3000`
- **Redirect URLs**: add
  - `http://localhost:3000/**`
  - your production origin(s)

## 4. Connect Resend as the auth mail provider

Supabase sends signup-confirmation and password-reset mail. Route it through
Resend SMTP so mail is delivered from your domain:

1. In Resend: add + verify your sending domain, create an **SMTP credential**
   (Resend → SMTP) — you get a host/user/password.
2. In Supabase: *Authentication → Emails → SMTP settings* → enable custom SMTP:
   - Host: `smtp.resend.com`, Port: `465` (SSL)
   - Username: `resend`, Password: `<resend smtp key>`
   - Sender email: e.g. `no-reply@yourdomain.example`
   - Minimum interval between emails: leave default for dev.
3. Customise the **Confirm signup** and **Reset password** template URLs if
   desired. The reset template must link to
   `<SITE_URL>/reset-password` (handled by Supabase via redirect).

> No Resend SDK/API key is needed in this repo unless application-level
> notifications are enabled later (`RESEND_API_KEY` placeholder already exists).
> All credentials live in environment files only — never in source.

## 5. Run the API

```bash
uvicorn answer_eval.api.main:create_app --factory --port 8300
# or: python -m answer_eval.api.main
```

Check `http://127.0.0.1:8300/api/healthz` — `"database": true` means the pool
connected.

## 6. Verify RLS

With the SQL editor (as `service_role` bypasses RLS), verify denial using the
anon role:

```sql
set local role anon;
select count(*) from assessments; -- must error / return no rows
```

The FastAPI backend always connects with the service-role credential and
derives teacher identity from verified JWTs (`answer_eval/api/deps.py`);
frontend code never receives the service-role key.
