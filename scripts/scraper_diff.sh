#!/usr/bin/env bash
# Print upstream changes since the vendored SHA. Never copies anything.
set -euo pipefail
FA="${FA:-/Users/shaicohen/git/finance-analysis}"
SHA=$(sed -n 's/^- SHA: //p' "$(dirname "$0")/../vendor/SOURCE.md")
git -C "$FA" fetch upstream
git -C "$FA" diff "$SHA" upstream/main -- scraper/ backend/utils/phone_numbers.py backend/utils/policy_ids.py
