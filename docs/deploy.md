# Deploying FreeRise to Railway

Nothing here is automated; follow the steps by hand. One Railway project, four pieces:

| Service | Source | Config file (Settings → Config-as-code) | Root directory |
|---|---|---|---|
| `api` | this repo | `/deploy/railway/api.json` (Dockerfile.api, healthcheck `/api/health`) | `/` |
| `worker` | this repo | `/deploy/railway/worker.json` (Dockerfile.worker, `freerise worker`) | `/` |
| `web` | this repo | `/deploy/railway/web.json` (web/Dockerfile, healthcheck `/login`) | `/web` |
| Postgres | Railway Postgres plugin (+ New → Database → PostgreSQL) | — | — |

The config-file path is always absolute from the repo root, even when the service has a root
directory (that is why `web.json` says `dockerfilePath: "Dockerfile"`).

The API runs `alembic upgrade head` on every start, so migrations ship with each deploy.
Only give `web` a public domain. `api` and `worker` stay private (the web app proxies `/api/*`
to the API over Railway's private network, so the session cookie stays same-origin).

## Variables

Set on **api** and **worker** (use a shared variable group or reference variables):

| Variable | Value |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}` — the `+psycopg` scheme is required; Railway's own `DATABASE_URL` starts with `postgresql://` and will not work as-is |
| `CREDENTIALS_KEY` | `python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"` — **back this up**; losing it makes every stored bank credential unreadable |
| `SESSION_SECRET` | another random value |
| `FREERISE_ENV` | `production` (secure cookies) |
| `TZ` | `Asia/Jerusalem` |

Set on **web**:

| Variable | Value |
|---|---|
| `API_URL` | `http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8000` — used at **build** time (Next.js rewrites are baked into the build; Railway passes service variables to the Dockerfile `ARG`) and at runtime. Change it → redeploy web. |
| `TZ` | `Asia/Jerusalem` |

For the api, also set `PORT=8000` so the private URL above is stable.

## Create the login user

The user is created once, inside the running API container:

```bash
railway ssh --service api freerise create-user shai
```

(`railway run freerise create-user shai` also works, but it runs on your machine with the service's
variables, so `DATABASE_URL` must point at the Postgres **public** proxy URL for that one command.)
Scan the printed `otpauth://` URI into an authenticator app; it is shown only once.

When setup is done (user created, optional RiseUp seed run), **remove the Postgres public TCP
proxy** (database service → Settings → Networking → delete the TCP proxy) so the database is
reachable only on Railway's private network. Re-add it temporarily for local dumps or one-off
commands, then remove it again.

Optional, to seed categorization rules from a RiseUp export (the `data/` folder is not in git,
so run this locally against the public DB URL): `uv run freerise categorize-seed-riseup`.

## Providers that block datacenter IPs

Some banks / card companies refuse logins from cloud IP ranges. Optionally route all scraper
traffic (Playwright browser and httpx clients) through a proxy by setting, on the **worker**
service only:

    FREERISE_SCRAPER_PROXY=http://user:pass@host:port

An Israeli residential/ISP proxy is recommended. This is optional; unset means direct connections.
The value contains credentials and is never logged. Leave it unset if your providers work without it.
Only the worker talks to providers.

## Mislaka (pension clearing house)

Mislaka is manual-only: the scheduled 07:00/14:00/21:00 runs skip it. Once a month (after the
report updates, around the 20th) press Sync on the Mislaka credential in the web app and answer
the SMS code. A reminder notification appears from the 21st if no successful sync happened that
month.

## Backups

- Enable Railway's Postgres backups (database service → Backups) with a daily schedule.
- Also take a local dump now and then:
  `pg_dump "$DATABASE_PUBLIC_URL" -Fc -f freerise-$(date +%F).dump`.
- Keep `CREDENTIALS_KEY` and `SESSION_SECRET` in a password manager. A DB backup without
  `CREDENTIALS_KEY` restores transactions but not the stored credentials.

## Demo data

Never on production. `demo-seed` refuses unless `FREERISE_ALLOW_DEMO=1` and refuses on any database
that already holds a real credential.
