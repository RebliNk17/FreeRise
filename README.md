<div align="center">

# FreeRise

**Free, open-source, self-hosted household finance for Israeli banks and credit cards.**

[![CI](https://github.com/RebliNk17/FreeRise/actions/workflows/ci.yml/badge.svg)](https://github.com/RebliNk17/FreeRise/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

</div>

<div dir="rtl">

**FreeRise** היא אפליקציה חינמית וקוד פתוח לניהול כלכלת הבית. היא מתחברת לבנקים ולחברות
האשראי בישראל, מושכת את התנועות אוטומטית, מסווגת אותן ומראה לך לאן הולך הכסף ומה צפוי בחודש
הבא. בלי מנוי, בלי פרסומות, והנתונים נשארים אצלך, על השרת שלך.

</div>

> FreeRise is an independent community project. It is not affiliated with, endorsed by, or
> connected to RiseUp or any bank or card company.

## Features

- **Automatic sync** from 19 Israeli banks and card companies: Hapoalim, Leumi, Discount,
  Mizrahi, Mercantile, Otsar Hahayal, Union, Beinleumi, Massad, Yahav, OneZero, Pepper, Pagi,
  Max, Cal, Isracard, Amex, Beyahad Bishvilha and Behatsdaa. Also the pension clearing house
  (Mislaka).
- **A home screen for the month**: what's left to spend this week, your month-end goal,
  variable spending week by week, the categories you track, fixed expenses, income, and a chart
  of where the money went. The month follows your pay cycle, not the calendar.
- **Auto-categorization** out of the box: about 950 built-in rules for common Israeli merchants,
  with the card company's own category as a fallback. Your choices always win, and you can import
  your categories from RiseUp.
- **Bank balances and upcoming card charges**, card by card.
- **Forecast** of next month: recurring charges, installments that end, and fixed income.
- **Card-bill reconciliation**: matches the debits on your bank account with the card statements.
- **Insights and notifications**, in the app and on Telegram.
- **Savings plans**, a what-if calculator and **pension tracking**.
- **Hebrew, RTL and mobile-first**. Installs on your phone as an app (PWA).
- **Private by design**: your data stays on your server, bank logins are encrypted (AES-GCM),
  and you sign in with a password and a 2FA code.

## Quick start with Docker

All you need is [Docker](https://docs.docker.com/get-docker/). This runs the published images,
so there is nothing to clone or build. It takes about two minutes.

**1. Download the setup and create your settings file**

```bash
mkdir freerise && cd freerise
curl -fsSLO https://raw.githubusercontent.com/RebliNk17/FreeRise/master/docker-compose.prebuilt.yml
curl -fsSL https://raw.githubusercontent.com/RebliNk17/FreeRise/master/.env.example | sed \
  -e "s|^CREDENTIALS_KEY=.*|CREDENTIALS_KEY=$(openssl rand -base64 32)|" \
  -e "s|^SESSION_SECRET=.*|SESSION_SECRET=$(openssl rand -base64 32)|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 16)|" > .env
```

This creates `.env` with fresh random secrets.

> [!IMPORTANT]
> **Back up `.env`**, especially `CREDENTIALS_KEY`. It encrypts your saved bank logins and your
> 2FA secret: without it you'd have to create a new login and enter every bank login again.

**2. Start FreeRise**

```bash
docker compose -f docker-compose.prebuilt.yml up -d
```

**3. Create your login**

```bash
docker compose -f docker-compose.prebuilt.yml exec api freerise create-user <your-username>
```

It asks for a password, then prints an `otpauth://` link **once**. Add it to your authenticator
app (Google Authenticator, 1Password, …) to get your 2FA codes.

**4. Open <http://localhost:3000>**, log in, and connect your banks and cards under
**הגדרות → חיבורים לבנקים ואשראי** (Settings → bank and card connections). FreeRise checks
each login and pulls your transactions right away. After that it syncs on its own at 07:00, 14:00
and 21:00 (change the hours under **הגדרות → סנכרון אוטומטי**).

### Everyday commands

Run these from the `freerise` folder:

| To | Run |
|---|---|
| Update to the newest release | `docker compose -f docker-compose.prebuilt.yml pull && docker compose -f docker-compose.prebuilt.yml up -d` |
| Stop (your data is kept) | `docker compose -f docker-compose.prebuilt.yml down` |
| See logs | `docker compose -f docker-compose.prebuilt.yml logs -f` |
| Add another user | `docker compose -f docker-compose.prebuilt.yml exec api freerise create-user <name>` |

Good to know:

- **Another app already uses port 3000?** Add `FREERISE_PORT=3001` to `.env` and open
  <http://localhost:3001>.
- **Versions**: `latest` is the newest release. For the newest build of `master`, add
  `FREERISE_VERSION=edge` to `.env`; to pin a release, use e.g. `FREERISE_VERSION=1.0.0`.
- **Apple Silicon Macs** run the images through emulation (the worker needs Google Chrome, which
  ships for Intel/AMD only). It works, just a little slower.

### Try it with demo data first

To look around before connecting real accounts, fill a **fresh, empty** install with about eight
months of made-up household data. Do this **instead of** step 3: demo data only goes into a
database that has no real user yet.

1. In `.env`, set `FREERISE_LOGIN_TOTP=false` so the demo user can log in without a 2FA code,
   then run `docker compose -f docker-compose.prebuilt.yml up -d` again.
2. Seed the demo:

   ```bash
   docker compose -f docker-compose.prebuilt.yml exec -e FREERISE_ALLOW_DEMO=1 api freerise demo-seed
   ```

3. Open <http://localhost:3000> and log in as **`demo`** with password **`demo-demo-demo`**.

**Done with the demo?** Wipe it:

```bash
docker compose -f docker-compose.prebuilt.yml down -v   # -v deletes the database, demo included
```

Then set `FREERISE_LOGIN_TOTP=true` in `.env` again and continue from step 2.

### Build from source

To run your own build instead of the published images:

```bash
git clone https://github.com/RebliNk17/FreeRise.git
cd FreeRise
cp .env.example .env              # then fill CREDENTIALS_KEY and SESSION_SECRET (openssl rand -base64 32)
docker compose up -d --build      # postgres, api, worker and web on http://localhost:3000
docker compose exec api freerise create-user <your-username>
```

Every command above works the same way here, without `-f docker-compose.prebuilt.yml`.

## Configuration

Everything is set in `.env`; [`.env.example`](.env.example) explains each line. After changing
it, run `docker compose … up -d` again to apply.

**Required**

| Variable | What it does |
|---|---|
| `CREDENTIALS_KEY` | Encrypts your saved bank logins and 2FA secrets. Generate with `openssl rand -base64 32`, and back it up. |
| `SESSION_SECRET` | Signs login sessions. Any long random value; changing it logs everyone out. |

**Optional**

| Variable | What it does |
|---|---|
| `FREERISE_PORT` | Port of the web app (Docker). Default `3000`. |
| `FREERISE_VERSION` | Image version (Docker): `latest` (default), `edge`, or a release like `1.0.0`. |
| `FREERISE_ENV` | Set to `production` when FreeRise is reachable from other devices over HTTPS: secure cookies, and 2FA is always required. |
| `FREERISE_LOGIN_TOTP` | `false` skips the 2FA code at login, for local testing. Ignored in production. |
| `FREERISE_SCRAPER_PROXY` | Sends bank traffic through a proxy (`http://user:pass@host:port`), for banks that block your server's IP. |
| `FREERISE_LLM_BASE_URL`, `FREERISE_LLM_API_KEY`, `FREERISE_LLM_MODEL` | Turn on the cash-flow Q&A chat over any OpenAI-compatible API (e.g. OpenRouter). Off unless all three are set. Only aggregated totals are sent. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | Database login (the quick start generates a random password). |

Telegram notifications are set up in the app, under **הגדרות → התראות** (Settings →
notifications). Scraper engine settings (`FREERISE_IBS_PROVIDERS`, `FREERISE_CHROME_PATH`, …)
are in [docs/scrapers.md](docs/scrapers.md).

### Running it for real

- Keep FreeRise on a machine you control and expose **only the web app** (port 3000). In
  `docker-compose.yml` the database and API listen on this machine only.
- To use it from your phone outside home, put it behind HTTPS (a reverse proxy such as Caddy, or
  a tunnel such as Tailscale or Cloudflare Tunnel) and set `FREERISE_ENV=production`.
- Back up the database volume and `.env` regularly.
- Prefer a managed host? See [deploying to Railway](docs/deploy.md).

## Categorization

FreeRise ships with built-in rules for common merchants
(`src/freerise/categorize/default_rules.py`); every sync categorizes new transactions, and the
home screen asks you about the ones it couldn't place. Your own choices are remembered and always
win.

**Coming from RiseUp?** Export your merchants from RiseUp to a pipe-separated file, then seed
your rules from it:

```bash
docker compose -f docker-compose.prebuilt.yml exec api freerise categorize-seed-riseup --path merchants.psv
```

(Copy the file into the container first, or run it from a source checkout with
`uv run freerise categorize-seed-riseup --path merchants.psv`.)

Upgrades can add built-in rules; they apply to new transactions. To re-categorize what you
already have right away (your manual choices and remembered rules are never changed):

```bash
docker compose -f docker-compose.prebuilt.yml exec api freerise categorize-defaults
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `port is already allocated` | Another app uses that port. For the web app set `FREERISE_PORT`; for Postgres (5432, build from source) stop the other database or change the port in `docker-compose.yml`. |
| The login page says the code is wrong | 2FA codes depend on the time: check your phone's and server's clocks. Lost your authenticator? There's no reset yet: create another user with `create-user` and a new name (all users see the same household data). |
| `demo-seed` says `refusing: real data exists` | Demo data only goes into an empty install. Use a fresh one (`down -v` deletes the database). |
| A bank keeps failing to log in | Log in on the bank's own site once (it may want a new password or terms). On cloud servers, banks often block the IP: set `FREERISE_SCRAPER_PROXY`. |
| After moving or restoring FreeRise, logins and bank syncs fail | `CREDENTIALS_KEY` in `.env` is not the original one. Restore it from your backup. |
| Something else | `docker compose -f docker-compose.prebuilt.yml logs -f api worker` usually says why. |

## Development

You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.14 for you), [Bun](https://bun.sh),
Node.js 22 or newer, Docker, and Google Chrome (the bank scrapers drive a real Chrome).

```bash
git clone https://github.com/RebliNk17/FreeRise.git && cd FreeRise
cp .env.example .env                                   # fill CREDENTIALS_KEY and SESSION_SECRET
docker compose up -d postgres                          # database on localhost:5432
uv run alembic upgrade head                            # create the tables
uv run freerise create-user <your-username>
(cd bridge && PUPPETEER_SKIP_DOWNLOAD=1 npm ci --ignore-scripts)   # scraper engine, see docs/scrapers.md
```

Then run each of these in its own terminal:

```bash
uv run uvicorn freerise.api.main:app --reload          # API on :8000
uv run freerise worker                                 # scheduled and on-demand syncs
cd web && bun install && bun dev                       # web on http://localhost:3000, /api goes to :8000
```

Tip: set `FREERISE_LOGIN_TOTP=false` in `.env` to skip the 2FA code while developing.

### Tests

```bash
uv run pytest -q                                       # needs Postgres; uses TEST_DATABASE_URL
uv run ruff check . && uv run ruff format --check .
cd web && bun test && bun run lint && bun run typecheck && bun run build
```

The test suite drops and recreates the `TEST_DATABASE_URL` database, so never point it at real
data.

### Project layout

| Path | What |
|---|---|
| `src/freerise/` | FastAPI API, sync worker, categorization, forecasting, insights |
| `web/` | Next.js web app (Hebrew, RTL) |
| `bridge/` | Node bridge that runs `israeli-bank-scrapers` (and our Pepper scraper) |
| `vendor/` | Vendored Python scrapers for providers the npm package doesn't cover |
| `alembic/` | Database migrations |
| `docs/` | [Scraper engines](docs/scrapers.md), [deploying to Railway](docs/deploy.md) |

## Security

FreeRise holds the keys to your bank accounts. Run it on infrastructure you control, keep `.env`
out of version control, and expose only the web app. To report a vulnerability, see
[SECURITY.md](SECURITY.md).

Scraping your own accounts may be subject to your bank's terms of service. You are responsible
for how you use this software.

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

## Thank you 🙏

FreeRise stands on the shoulders of these open-source projects:

- **[eshaham/israeli-bank-scrapers](https://github.com/eshaham/israeli-bank-scrapers)** (MIT):
  the community scraper library behind almost every bank and card integration here. Years of
  work by its maintainers and contributors made projects like this possible.
- **[tomerroditi/finance-analysis](https://github.com/tomerroditi/finance-analysis)**
  (Apache-2.0): its Python scrapers are vendored in `vendor/` and power the Mislaka pension
  integration. See [vendor/SOURCE.md](vendor/SOURCE.md) for what we changed.

And the frameworks: [FastAPI](https://fastapi.tiangolo.com), [SQLAlchemy](https://www.sqlalchemy.org),
[Playwright](https://playwright.dev), [Next.js](https://nextjs.org), [Recharts](https://recharts.org)
and [PostgreSQL](https://www.postgresql.org).

## License

[Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for third-party attributions.
