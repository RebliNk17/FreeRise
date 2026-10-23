# Vendored source

- Upstream: git@github.com:tomerroditi/finance-analysis.git
- SHA: 9a88bdf457126e8b31b241f88e71f95e9893795b

Copied paths:
- `scraper/` -> `vendor/fa_scraper/scraper/` (excluding `__pycache__`)
- `backend/utils/phone_numbers.py`, `backend/utils/policy_ids.py` -> `vendor/fa_backend_utils/backend/utils/`
  (stdlib-only; `backend/__init__.py` and `backend/utils/__init__.py` are empty stubs, since the originals import unrelated backend modules)

Local patches (re-apply after a vendor refresh; all marked `# freerise patch: proxy`):
- `scraper/utils/proxy.py` (new), `scraper/base/browser_scraper.py`, `scraper/base/api_scraper.py`,
  `scraper/utils/fetch.py`, `scraper/providers/banks/onezero.py`: route Playwright launch and httpx
  clients through env `FREERISE_SCRAPER_PROXY` when set.
