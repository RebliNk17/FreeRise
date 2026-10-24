# Scraper engines

Two engines run bank/card scrapes; `freerise.sync.demo_provider.make_scraper` picks one per provider.

- **npm package** [`israeli-bank-scrapers`](https://github.com/eshaham/israeli-bank-scrapers),
  pinned in `bridge/package.json`, driven by `bridge/run.mjs` over a JSON-lines stdio protocol
  (adapter: `src/freerise/sync/ibs.py`). Runs every provider the package has (`ibs.COMPANIES`):
  all banks (incl. OneZero), Max, Cal, Isracard, Amex, Beyahad Bishvilha, Behatsdaa.
- **Pepper**: the package has no Pepper scraper, so the bridge runs its own (`bridge/pepper.mjs`)
  over the same protocol; `run.mjs` picks it for `companyId: "pepper"`.
- **vendored Python port** (`vendor/fa_scraper`) only for providers the package doesn't have:
  Mislaka (pension clearing house) and HaPhoenix (insurance, deprecated in favour of Mislaka).

`FREERISE_IBS_PROVIDERS` picks the providers that use the package: `all` (default; new mappings are
included automatically), an explicit comma list (`visa cal,amex`), or `all,-max` to put one back
on Python. `""` = everything on Python. Restart the worker after changing it. Both engines produce
the same `txn_key`s and account numbers for Max and Cal (`tests/sync/test_ibs_parity.py`), so
switching back and forth never duplicates rows. Other providers have no stored data yet; their
package output is normalised the same way (`test_generic_mapping` in `tests/sync/test_ibs.py`):
Israel-local dates, identifiers as text, zero amounts as `-0.0`, empty memo as `None`.

Stored credential field names are the package's own `loginFields` for every provider
(`test_mapping_matches_package_definitions`), so existing encrypted credentials keep working.
OneZero: the bridge answers the package's `otpCodeRetriever` with FreeRise's OTP prompt, normalises
`05x…` phone numbers to `+9725…`, and returns a newly minted long-term token as
`freeriseOtpLongTermToken`, which `service.py` stores in the credential (`otpLongTermToken`).

**Login safety net** (all providers, both engines): when the last 2 runs of a connection
(schedule or manual) failed before reaching data fetch (wrong details, lock screen, timeout or
general error on the login page), scheduled syncs skip it (`service.login_paused`) and an in-app
notification asks the owner to check the login on the provider's site and press "סנכרון". A
successful run (manual sync or verify) resumes scheduling. Recognised wrong-password / blocked
errors still disable the connection outright, as before.

Env: `FREERISE_CHROME_PATH` (default: macOS Chrome, `/opt/google/chrome/chrome` on Linux),
`FREERISE_SCRAPER_PROXY` (Chrome `--proxy-server` + Node's env proxy for API calls),
`FREERISE_IBS_TIMEOUT_S` (whole run, default 1500).

## Local setup

```bash
cd bridge && PUPPETEER_SKIP_DOWNLOAD=1 npm ci --ignore-scripts
```

`--ignore-scripts` is safe: the only install script in the tree is puppeteer's browser download,
and the bridge uses the installed Google Chrome instead.

## Upgrading the package

1. Bump the **exact** version in `bridge/package.json` (no `^`/`~`), then
   `PUPPETEER_SKIP_DOWNLOAD=1 npm install --ignore-scripts` and commit `package-lock.json`.
2. Diff the published code against the previous pin, e.g.
   `npm diff --diff=israeli-bank-scrapers@OLD --diff=israeli-bank-scrapers@NEW` (the `lib/*.js`
   files carry the TypeScript source in their inline source maps). Review:
   - **Network**: every URL / `fetch` / `page.goto` still targets the providers' own domains
     (`*.max.co.il`, `*.cal-online.co.il`, ...); no new hosts, no telemetry, no analytics.
   - **Credentials**: only typed into the provider's login form / sent to its auth endpoint;
     never logged (`debug(...)`), written to disk, or put in URLs.
   - **Code loading**: no `eval`, `new Function`, `child_process`, dynamic `require` of remote
     code; no new install scripts (`hasInstallScript` in `package-lock.json`).
   - **Dependencies**: new or changed packages in the lockfile; `npm audit --omit=dev`.
   - **Mapping** (each scraper's `fetchData` / transaction mapping, Max and Cal first since they
     hold data): anything that changes `identifier`, dates, amounts or `accountNumber` re-keys
     stored rows.
   - **Hooks the bridge relies on**: `scraper.login` (returns `{success, persistentOtpToken?}`),
     OneZero's `getLongTermTwoFactorToken`, the `unexpected login result "X"` message, the
     `CompanyTypes` / `SCRAPERS[].loginFields` names (`tests/sync/test_ibs.py` checks the last).
3. `uv run pytest tests/sync/test_ibs.py tests/sync/test_ibs_parity.py` (runs the new package's
   real Max / Cal mapping code against canned responses and compares with the Python engine, and
   the real OneZero flow through `run.mjs` against a stubbed API), then the full `uv run pytest`.
4. Rebuild the worker image (`Dockerfile.worker` runs `npm ci --ignore-scripts`).

Never set `DEBUG` on the worker: the package's `debug()` output includes account data. The
bridge receives credentials on stdin only (never argv / env) and prints protocol lines only.
