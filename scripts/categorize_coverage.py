"""How many transaction descriptions the shipped default rules categorize. Never touches a DB.

Usage: uv run python scripts/categorize_coverage.py descriptions.txt [--unmatched N]
One description per line (text after a "|" is ignored, so a RiseUp psv works too); "-" reads
stdin. Export descriptions yourself, e.g. psql -At -c "SELECT description FROM transactions".
"""

import argparse
import sys

from freerise.categorize.default_rules import coverage


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("path")
    p.add_argument("--unmatched", type=int, default=20, help="how many unmatched to list")
    a = p.parse_args()
    f = sys.stdin if a.path == "-" else open(a.path, encoding="utf-8")  # noqa: SIM115
    lines = [ln.split("|")[0].strip() for ln in f if ln.strip() and not ln.startswith("#")]
    hits, missed = coverage(lines)
    n = len(lines)
    print(f"{n - len(missed)}/{n} matched ({(n - len(missed)) / max(n, 1):.0%})")
    for cat, k in hits.most_common():
        print(f"  {k:5d}  {cat}")
    if missed and a.unmatched:
        print("unmatched:")
        for d in missed[: a.unmatched]:
            print(f"  {d}")


if __name__ == "__main__":
    main()
