import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.categorize.pipeline import categorize_pending, uncategorized_merchants
from freerise.categorize.seed import seed_from_riseup
from freerise.models import Category, MerchantRule


def export_uncategorized(session: Session, out: Path) -> int:
    rows = uncategorized_merchants(session)
    with Path(out).open("w", encoding="utf-8") as f:
        f.writelines(json.dumps(rec, ensure_ascii=False) + "\n" for rec in rows)
    return len(rows)


def import_rules(session: Session, path: Path) -> tuple[int, int]:
    """Returns (rules written, rows skipped for unknown category). Then categorizes pending."""
    cats = {c.name: c.id for c in session.scalars(select(Category))}
    written = skipped = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        cid = cats.get(rec["category"])
        if cid is None or not rec["merchant_key"]:
            skipped += 1
            continue
        rule = session.scalar(
            select(MerchantRule).where(
                MerchantRule.pattern == rec["merchant_key"], MerchantRule.match == "exact"
            )
        )
        if rule is None:
            session.add(
                MerchantRule(
                    pattern=rec["merchant_key"], match="exact", category_id=cid, source="ai"
                )
            )
        elif rule.source != "user":
            rule.category_id, rule.source = cid, "ai"
        else:
            continue
        written += 1
    session.flush()
    categorize_pending(session)
    return written, skipped


def _export(args: argparse.Namespace) -> None:
    from freerise.db import SessionLocal

    with SessionLocal.begin() as s:
        print(f"exported {export_uncategorized(s, Path(args.out))} merchants")


def _import(args: argparse.Namespace) -> None:
    from freerise.db import SessionLocal

    with SessionLocal.begin() as s:
        w, k = import_rules(s, Path(args.infile))
    print(f"imported {w} rules, skipped {k}")


def _seed(args: argparse.Namespace) -> None:
    from freerise.db import SessionLocal

    with SessionLocal.begin() as s:
        n = seed_from_riseup(s, Path(args.path))
        categorize_pending(s)
    print(f"seeded {n} rules")


def _import_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--in", dest="infile", required=True)


def _seed_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--path", default="data/riseup/merchants.psv")


COMMANDS = {
    "categorize-export": (lambda p: p.add_argument("--out", required=True), _export),
    "categorize-import": (_import_args, _import),
    "categorize-seed-riseup": (_seed_args, _seed),
}
