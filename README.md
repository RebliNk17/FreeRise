<div align="center">

# FreeRise

**Free, open-source, self-hosted household finance for Israeli banks and credit cards.**

[![CI](https://github.com/RebliNk17/freerise/actions/workflows/ci.yml/badge.svg)](https://github.com/RebliNk17/freerise/actions/workflows/ci.yml)
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

- **Automatic sync** from 18 Israeli banks and card companies: Hapoalim, Leumi, Discount,
  Mizrahi, Mercantile, Otsar Hahayal, Union, Beinleumi, Massad, Yahav, OneZero, Pagi, Max,
  Cal, Isracard, Amex, Beyahad Bishvilha and Behatsdaa. Also the pension clearing house (Mislaka).
- **Auto-categorization** with merchant rules. Coming from RiseUp? Import your RiseUp merchant
  categories to start with them.
- **Monthly cash-flow cycles**, budgets, savings plans and a what-if calculator.
- **Forecast** of next month: recurring charges, installments and fixed income.
- **Card-bill reconciliation**: matches bank debits with card statements.
- **Insights and notifications** (in-app and Telegram).
- **Pension tracking**: funds and returns.
- **Hebrew, RTL, mobile-first** web app that installs as a PWA.
- **Private by design**: bank credentials are encrypted at rest (AES-GCM), and login uses
  password plus TOTP 2FA.

## Quick start (Docker)

You need [Docker](https://docs.docker.com/get-docker/).

```bash
git clone https://github.com/RebliNk17/freerise.git
cd freerise
cp .env.example .env
```

Generate two secrets and paste them into `.env` as `CREDENTIALS_KEY` and `SESSION_SECRET`:

```bash
python3 -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
```

> **Back up `CREDENTIALS_KEY`.** If you lose it, every stored bank credential becomes unreadable.

Start everything and create your user:

```bash
docker compose up -d --build                         # postgres, api :8000, worker, web :3000
docker compose exec api freerise create-user <your-username>
```

`create-user` asks for a password and prints a TOTP URI once. Add it to your authenticator app
(Google Authenticator, 1Password, etc.). Then open <http://localhost:3000>, log in, and connect
your banks under **Settings → Credentials**.

`docker compose down` stops everything and keeps the database volume.

### Try it with demo data

To explore without connecting real accounts, fill an **empty** database with about eight
months of fake household data and a `demo` user:

```bash
docker compose exec -e FREERISE_ALLOW_DEMO=1 api freerise demo-seed   # password: demo-demo-demo
```

Demo seeding refuses to run if any real credential exists, so it never mixes with real data.

## Development

Prerequisites: [uv](https://docs.astral.sh/uv/), [Bun](https://bun.sh), Node.js 24, Docker,
and Google Chrome (the scrapers drive real Chrome).

```bash
cp .env.example .env                                   # fill CREDENTIALS_KEY and SESSION_SECRET
docker compose up -d postgres
uv run alembic upgrade head
uv run freerise create-user <your-username>
uv run uvicorn freerise.api.main:app --reload          # API on :8000
(cd bridge && npm ci --ignore-scripts)                 # scraper engine, see docs/scrapers.md
uv run freerise worker                                 # scheduled and on-demand syncs
cd web && bun install && bun dev                       # web on :3000, proxies /api to :8000
```

### Tests

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
cd web && bun test && bun run lint && bun run build
```

### Project layout

| Path | What |
|---|---|
| `src/freerise/` | FastAPI API, sync worker, categorization, forecasting, insights |
| `web/` | Next.js web app (Hebrew, RTL) |
| `bridge/` | Node bridge that runs `israeli-bank-scrapers` |
| `vendor/` | Vendored Python scrapers for providers the npm package doesn't cover |
| `alembic/` | Database migrations |
| `docs/` | [Scraper engines](docs/scrapers.md), [deploying to Railway](docs/deploy.md) |

## Importing from RiseUp

Export your merchants from RiseUp to a pipe-separated file, then seed the merchant rules:

```bash
uv run freerise categorize-seed-riseup --path merchants.psv
```

## Configuration

All settings are environment variables. See [`.env.example`](.env.example) for the full list.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection (`postgresql+psycopg://...`) |
| `CREDENTIALS_KEY` | 32-byte base64 key that encrypts bank credentials |
| `SESSION_SECRET` | Signs login sessions |
| `FREERISE_ENV` | `production` turns on secure cookies and enforced 2FA |
| `FREERISE_SCRAPER_PROXY` | Optional proxy for scraper traffic |
| `FREERISE_IBS_PROVIDERS` | Which providers use the npm scraper engine ([docs](docs/scrapers.md)) |

## Security

FreeRise holds the keys to your bank accounts. Run it on infrastructure you control, keep
`.env` out of version control, and expose only the web service. To report a vulnerability,
see [SECURITY.md](SECURITY.md).

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
