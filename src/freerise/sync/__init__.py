import sys
from pathlib import Path

# Make the vendored `scraper` and `backend.utils` packages importable (see vendor/SOURCE.md).
_vendor = Path(__file__).resolve().parents[3] / "vendor"
for _p in (_vendor / "fa_scraper", _vendor / "fa_backend_utils"):
    if str(_p) not in sys.path:
        sys.path.append(str(_p))
