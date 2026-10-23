from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from freerise.models import Account, Category, MerchantRule, Transaction

# Scraper `Transaction.category` text -> our category name. Extend as real strings show up.
PROVIDER_CATEGORY_MAP: dict[str, str] = {
    "מזון וצריכה": "כלכלה",
    "מסעדות": "אוכל בחוץ",
    "דלק": "רכב",
    "תקשורת": "תקשורת",
}

# rule source -> Transaction.category_source
_SOURCE = {"user": "rule", "seed": "map", "ai": "ai", "provider": "provider"}


def _match(rules: list[MerchantRule], key: str, desc: str) -> MerchantRule | None:
    for r in rules:
        if r.match == "exact" and r.pattern == key:
            return r
    for r in rules:
        pat = (r.pattern or "").lower()
        if r.match == "contains" and pat and (pat in key or pat in desc):
            return r
    return None


def categorize_transaction(
    session: Session,
    txn: Transaction,
    providers: list[str] | None = None,
    rules: list[MerchantRule] | None = None,
    *,
    account_kind: str | None = None,
    card_bill_ids: set[int] | None = None,
) -> tuple[int | None, str | None]:
    """Order: user rules, other rules, provider category hint. `providers` = extra hint texts.
    Non-user card-bill rules only apply to bank accounts (and win there): on a card statement a
    description like "דמי כרטיס ישראכרט" is a fee, not the card's bill."""
    if rules is None:
        rules = list(session.scalars(select(MerchantRule)))
    if account_kind is None:
        account_kind = session.scalar(select(Account.kind).where(Account.id == txn.account_id))
    others = [r for r in rules if r.source != "user"]
    if card_bill_ids is None:
        card_bill_ids = _card_bill_ids(session)
    if account_kind == "card":
        others = [r for r in others if r.category_id not in card_bill_ids]
    else:  # a bank-side bill beats other contains rules (fee patterns like "דמי כרטיס")
        others.sort(key=lambda r: r.category_id not in card_bill_ids)
    key, desc = txn.merchant_key or "", (txn.description or "").lower()
    users = [r for r in rules if r.source == "user"]
    for group in (users, others):
        r = _match(group, key, desc)
        if r:
            return r.category_id, _SOURCE[r.source]
    for hint in [txn.provider_category, *(providers or [])]:
        name = PROVIDER_CATEGORY_MAP.get(hint or "")
        if name:
            cid = session.scalar(select(Category.id).where(Category.name == name))
            if cid:
                return cid, "provider"
    return None, None


def _card_bill_ids(session: Session) -> set[int]:
    return set(session.scalars(select(Category.id).where(Category.group == "card_bill")))


def categorize_pending(session: Session) -> int:
    rules = list(session.scalars(select(MerchantRule)))
    bill_ids = _card_bill_ids(session)
    n = 0
    rows = session.execute(
        select(Transaction, Account.kind)
        .join(Account, Account.id == Transaction.account_id)
        .where(Transaction.category_id.is_(None))
    ).all()
    for t, kind in rows:
        cid, src = categorize_transaction(
            session, t, rules=rules, account_kind=kind, card_bill_ids=bill_ids
        )
        if cid is not None:
            t.category_id, t.category_source = cid, src
            n += 1
    session.flush()
    return n


def _remember(session: Session, merchant_key: str, category_id: int) -> None:
    """Upsert the user's exact rule for this merchant."""
    rule = session.scalar(
        select(MerchantRule).where(
            MerchantRule.pattern == merchant_key, MerchantRule.match == "exact"
        )
    )
    if rule:
        rule.category_id, rule.source = category_id, "user"
    else:
        session.add(
            MerchantRule(
                pattern=merchant_key, match="exact", category_id=category_id, source="user"
            )
        )


def set_merchant_category(
    session: Session, merchant_key: str, category_id: int, apply_to_past: bool = True
) -> int:
    """Bulk: remember a user rule for the merchant, then categorize its uncategorized txns
    (and, with apply_to_past, every non-manual one). Returns rows changed."""
    _remember(session, merchant_key, category_id)
    cond = Transaction.category_id.is_(None)
    if apply_to_past:
        cond = or_(
            cond, Transaction.category_source.is_(None), Transaction.category_source != "manual"
        )
    res = session.execute(
        update(Transaction)
        .where(Transaction.merchant_key == merchant_key, cond)
        .values(category_id=category_id, category_source="rule")
    )
    session.flush()
    session.expire_all()
    return res.rowcount


def uncategorized_merchants(session: Session) -> list[dict]:
    """Uncategorized transactions grouped by merchant, most frequent first."""
    rows = session.execute(
        select(
            Transaction.merchant_key,
            func.min(Transaction.description),
            func.count(),
            func.sum(Transaction.amount),
            func.min(Account.kind),
        )
        .join(Account, Account.id == Transaction.account_id)
        .where(
            Transaction.category_id.is_(None),
            Transaction.merchant_key != "",
            Account.excluded.is_(False),
        )
        .group_by(Transaction.merchant_key)
        .order_by(func.count().desc(), Transaction.merchant_key)
    ).all()
    return [
        {
            "merchant_key": key,
            "sample_description": desc,
            "count": n,
            "total": float(total),
            "kind": "card" if kind == "card" else "bank",
        }
        for key, desc, n, total, kind in rows
    ]


def set_category(
    session: Session,
    txn_id: int,
    category_id: int,
    remember: bool = True,
    apply_to_past: bool = False,
) -> int:
    """Manual change. Returns rows changed (the transaction itself plus any applied to past)."""
    txn = session.get(Transaction, txn_id)
    if txn is None:
        raise ValueError(f"transaction {txn_id} not found")
    txn.category_id, txn.category_source = category_id, "manual"
    changed = 1
    if remember and txn.merchant_key:
        _remember(session, txn.merchant_key, category_id)
    if apply_to_past and txn.merchant_key:
        res = session.execute(
            update(Transaction)
            .where(
                Transaction.merchant_key == txn.merchant_key,
                Transaction.id != txn.id,
                or_(Transaction.category_source.is_(None), Transaction.category_source != "manual"),
            )
            .values(category_id=category_id, category_source="rule")
        )
        changed += res.rowcount
    session.flush()
    session.expire_all()
    return changed
