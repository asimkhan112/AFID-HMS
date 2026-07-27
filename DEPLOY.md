# AFID HMS — Deployment Guide (Neon · Railway · Vercel)

Three managed services, one per tier:

| Tier | Service | What it hosts |
|------|---------|---------------|
| Database | **Neon** | Managed PostgreSQL |
| Backend | **Railway** | FastAPI app (`AFID backend/`) |
| Frontend | **Vercel** | Static portals (`AFID frontend/AFID frontend/`) |

**How they connect:** the browser only ever talks to Vercel. Vercel serves the
static HTML and *rewrites* API paths (`/auth`, `/patients`, `/hod`, …) to the
Railway backend server-side — so there is **no CORS and no hard-coded backend URL
in the client**. Railway talks to Neon over an SSL connection string.

```
Browser ──▶ Vercel (static + /api rewrites) ──▶ Railway (FastAPI) ──▶ Neon (Postgres)
```

Do the steps in order: **Neon → Railway → Vercel** (each needs the previous one's output).

---

## 1 · Neon — create the database

1. Sign in at **neon.tech** → **New Project** (pick a region near your Railway region).
2. Open the project → **Connection Details** → copy the **connection string**. It looks like:
   ```
   postgresql://<user>:<password>@<host>.neon.tech/<db>?sslmode=require
   ```
   Use the **pooled** connection string if offered (better for serverless-style traffic).
3. Keep this string — it becomes Railway's `DATABASE_URL`.

> Tables are created automatically on first backend boot (`Base.metadata.create_all`),
> and the seed scripts run on start (see Railway below), so there is nothing to run here.

---

## 2 · Railway — deploy the backend

1. Sign in at **railway.app** → **New Project** → **Deploy from GitHub repo** → pick `AFID-HMS`.
2. **Settings → Root Directory:** set to `AFID backend`  ← important (the repo has front/back-end side by side).
3. Railway auto-detects Python and installs `requirements.txt`. The included files handle the rest:
   - `Procfile` → start command: seeds idempotently, then serves
     `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - `.python-version` → pins Python 3.12
4. **Variables** (Settings → Variables) — add:

   | Key | Value |
   |-----|-------|
   | `DATABASE_URL` | the Neon connection string from step 1 |
   | `SECRET_KEY` | a fresh 64-char random string (see below) |
   | `CORS_ORIGINS` | `["https://<your-app>.vercel.app"]` (optional with the proxy; harmless to set) |

   Generate a strong secret:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
5. Deploy. Watch the logs — you want:
   ```
   ✅  Database seeded successfully!
   INFO:     Uvicorn running on http://0.0.0.0:$PORT
   ```
6. **Settings → Networking → Generate Domain.** Copy the public URL, e.g.
   `https://afid-backend-production.up.railway.app`. You'll paste it into Vercel next.
7. Sanity check in a browser: `https://<railway-url>/` should return
   `{"status":"ok",...}`, and `/docs` shows the API.

**Default seeded logins** (change the passwords after first login):
`hod@afid.mil / admin1234` · `doctor@afid.mil / doctor1234` · `reception@afid.mil / staff1234`

---

## 3 · Vercel — deploy the frontend

1. **Edit `AFID frontend/AFID frontend/vercel.json`** and replace every
   `REPLACE_WITH_RAILWAY_URL` with your Railway host (no `https://`, no trailing slash),
   e.g. `afid-backend-production.up.railway.app`. Commit & push.
2. Sign in at **vercel.com** → **Add New → Project** → import `AFID-HMS`.
3. Configure:
   - **Root Directory:** `AFID frontend/AFID frontend`
   - **Framework Preset:** **Other**
   - **Build Command:** *(leave empty)* — these are plain static files, no build step
   - **Output Directory:** *(leave empty / `.`)*
4. Deploy. Open the Vercel URL — it should redirect to `Login.html`; log in with a seeded account.

`vercel.json` (already in the repo) forwards these prefixes to Railway:
`/auth /patients /doctors /allocations /procedures /leaves /staff /hod /presets`.

---

## 4 · Verify end-to-end

- Load the Vercel URL → **Login** as `hod@afid.mil / admin1234`.
- The HOD dashboard KPIs, rooms, and monitoring should populate (those hit
  `/hod/summary`, `/hod/rooms`, `/hod/monitoring` through the proxy).
- In browser DevTools → Network, API calls should be **same-origin** (your Vercel
  domain) returning 200 — no CORS errors.

---

## Notes & gotchas

- **Redeploys:** push to `main` → Railway and Vercel auto-redeploy. The seed scripts
  are idempotent (they skip if data already exists), so restarts are safe.
- **Changing the backend URL later:** edit only `vercel.json` and redeploy the
  frontend — nothing in the app code hard-codes the backend address.
- **Secrets:** `.env` is gitignored and is **not** used in production — Railway
  injects the real values as environment variables. Never commit real secrets.
- **Local dev is unchanged:** run the backend on `:8000` and the frontend with
  `npm run dev` (Vite on `:5173`). `api.js` now uses same-origin paths, which the
  Vite proxy (`vite.config.js`) forwards to `:8000` — mirroring the Vercel rewrites.
- **File names with spaces** (`doctor (1).html`): these are served fine by Vercel,
  but if you ever see a 404 on the doctor portal, that's the first thing to check.
- **Free-tier sleep:** Railway/Neon free tiers may cold-start; the first request
  after idle can take a few seconds.
