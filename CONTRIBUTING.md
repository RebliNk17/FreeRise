# Contributing to FreeRise

Thanks for helping. Bug reports, new bank support, fixes, translations and docs are all welcome.

## Before you start

- For anything bigger than a small fix, open an issue first so we can agree on the approach.
- Never paste real bank data, credentials, account numbers or screenshots with personal details
  into issues, PRs, tests or fixtures. Use fake data.
- Security problems go through [SECURITY.md](SECURITY.md), not public issues.

## Setup

Follow **Development** in the [README](README.md). Tests need a running Postgres
(`docker compose up -d postgres`) and `TEST_DATABASE_URL` in `.env`. The test suite drops and
recreates that database, so never point it at real data.

## Making a change

1. Fork the repo and create a branch from `master`.
2. Make your change and add or update tests.
3. Run the checks:

   ```bash
   uv run ruff check . && uv run ruff format --check .
   uv run pytest -q
   cd web && bun run lint && bun test && bun run build
   ```

4. Use [Conventional Commits](https://www.conventionalcommits.org) for commit messages, for
   example `feat(sync): support Bank X` or `fix(web): wrong total on cash-flow page`.
5. Open a pull request. CI must pass before merge.

## Database changes

Add an Alembic migration under `alembic/versions/` for every model change:

```bash
uv run alembic revision --autogenerate -m "short description"
```

## Scrapers

Most providers run through [israeli-bank-scrapers](https://github.com/eshaham/israeli-bank-scrapers).
If a bank breaks or is missing, the fix often belongs upstream there. Read
[docs/scrapers.md](docs/scrapers.md) before changing `bridge/` or `vendor/`.

## Code of conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
