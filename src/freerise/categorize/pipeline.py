from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, joinedload

from freerise.accounts import account_holder, account_labels
from freerise.categorize.default_rules import provider_category
from freerise.categorize.normalize import best_match
from freerise.forecast.recurring import AUTO_AMOUNT, AUTO_N
from freerise.models import Account, Category, MerchantRule, RecurringItem, Transaction

# rule source -> Transaction.category_source
_SOURCE = {"user": "rule", "seed": "map", "ai": "ai", "provider": "provider", "default": "default"}
# Assigned automatically from default rules or the card company's category: re-evaluated by
# recategorize_auto; everything else (manual, user rules, seed, ai) is left alone.
AUTO_SOURCES = ("default", "provider")
OTHER_INCOME = "הכנסות אחרות"
OWN_TRANSFER_DAYS = 4  # an own-account transfer's outgoing twin lands within this many days


def _exact(rules: list[MerchantRule], key: str) -> MerchantRule | None:
    return next((r for r in rules if r.match == "exact" and r.pattern == key), None)


def _contains(rules: list[MerchantRule], key: str, desc: str) -> MerchantRule | None:
    return best_match(((r.pattern, r) for r in rules if r.match == "contains"), key, desc)


def _own_names(session: Session) -> set[str]:
    # ponytail: names under 4 chars (initials, test owners) would match almost anything
    accounts = session.scalars(select(Account).options(joinedload(Account.credential)))
    return {n for a in accounts if len(n := account_holder(a).strip()) >= 4}


def _own_transfer(session: Session, txn: Transaction) -> bool:
    """Incoming money that is really ours moving: the sender part of the description names an
    account holder ("ביט/ישראל ישראלי") or says it's ours ("מפייבוקס שלי"), or another of our bank accounts sent the same amount then."""
    sender = (txn.description or "").split(" ל-")[0]  # "העברה מ- X ל- <us>": only X is the sender
    if "שלי" in sender.split() or any(n in sender for n in _own_names(session)):
        return True
    return (
        session.scalar(
            select(Transaction.id)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Account.kind == "bank",
                Transaction.account_id != txn.account_id,
                Transaction.amount.between(-txn.amount - 1, -txn.amount + 1),
                Transaction.date.between(
                    txn.date - timedelta(days=OWN_TRANSFER_DAYS),
                    txn.date + timedelta(days=OWN_TRANSFER_DAYS),
                ),
            )
            .limit(1)
        )
        is not None
    )


def categorize_transaction(
    session: Session,
    txn: Transaction,
    providers: list[str] | None = None,
    rules: list[MerchantRule] | None = None,
    *,
    account_kind: str | None = None,
    card_bill_ids: set[int] | None = None,
    cat_ids: dict[str, int] | None = None,
) -> tuple[int | None, str | None]:
    """_match, except that incoming money into a bank account that a non-user rule calls a
    transfer counts as other income unless it's our own (_own_transfer): "העברה" alone says
    nothing about who sent it, and hiding a payment from someone else hides real income."""
    if account_kind is None:
        account_kind = session.scalar(select(Account.kind).where(Account.id == txn.account_id))
    cid, src = _match(
        session,
        txn,
        providers,
        rules,
        account_kind=account_kind,
        card_bill_ids=card_bill_ids,
        cat_ids=cat_ids,
    )
    if cid is None or src == "rule" or account_kind != "bank" or txn.amount <= 0:
        return cid, src
    if session.scalar(select(Category.group).where(Category.id == cid)) != "transfer":
        return cid, src
    if _own_transfer(session, txn):
        return cid, src
    other = session.scalar(select(Category.id).where(Category.name == OTHER_INCOME))
    return (other, src) if other else (cid, src)


def _match(
    session: Session,
    txn: Transaction,
    providers: list[str] | None = None,
    rules: list[MerchantRule] | None = None,
    *,
    account_kind: str | None = None,
    card_bill_ids: set[int] | None = None,
    cat_ids: dict[str, int] | None = None,
) -> tuple[int | None, str | None]:
    """Order: user rules (exact, contains), other exact rules, other contains rules (seed and
    default; earliest then longest match wins), then the card company's category. `providers` =
    extra hint texts. Non-user card-bill rules only apply to bank accounts (and win there): on a
    card statement a description like "דמי כרטיס ישראכרט" is a fee, not the card's bill."""
    if rules is None:
        rules = list(session.scalars(select(MerchantRule)))
    if account_kind is None:
        account_kind = session.scalar(select(Account.kind).where(Account.id == txn.account_id))
    if card_bill_ids is None:
        card_bill_ids = _card_bill_ids(session)
    key, desc = txn.merchant_key or "", (txn.description or "").lower()
    users = [r for r in rules if r.source == "user"]
    others = [r for r in rules if r.source != "user"]
    bills = [r for r in others if r.category_id in card_bill_ids]
    rest = [r for r in others if r.category_id not in card_bill_ids]
    r = (
        _exact(users, key)
        or _contains(users, key, desc)
        or _exact(rest if account_kind == "card" else others, key)
        or (None if account_kind == "card" else _contains(bills, key, desc))
        or _contains(rest, key, desc)
    )
    if r:
        return r.category_id, _SOURCE[r.source]
    for hint in [txn.provider_category, *(providers or [])]:
        name = provider_category(hint)
        if name:
            if cat_ids is None:
                cid = session.scalar(select(Category.id).where(Category.name == name))
            else:
                cid = cat_ids.get(name)
            if cid:
                return cid, "provider"
    return None, None


def _card_bill_ids(session: Session) -> set[int]:
    return set(session.scalars(select(Category.id).where(Category.group == "card_bill")))


def _recategorize(session: Session, cond) -> int:
    rules = list(session.scalars(select(MerchantRule)))
    bill_ids = _card_bill_ids(session)
    cat_ids = {c.name: c.id for c in session.scalars(select(Category))}
    n = 0
    rows = session.execute(
        select(Transaction, Account.kind)
        .join(Account, Account.id == Transaction.account_id)
        .where(cond)
    ).all()
    for t, kind in rows:
        cid, src = categorize_transaction(
            session, t, rules=rules, account_kind=kind, card_bill_ids=bill_ids, cat_ids=cat_ids
        )
        if cid is None and t.category_id is None:
            continue  # still unknown: keep any category_source as is
        if (cid, src) != (t.category_id, t.category_source):
            t.category_id, t.category_source = cid, src
            n += 1
    session.flush()
    return n


def categorize_pending(session: Session) -> int:
    """Categorize uncategorized transactions; returns how many got a category."""
    return _recategorize(session, Transaction.category_id.is_(None))


def reclassify_incoming_transfers(session: Session) -> int:
    """Re-run the pipeline on incoming bank rows that a non-user rule filed as transfers, so
    payments from other people become income (see categorize_transaction)."""
    transfer = select(Category.id).where(Category.group == "transfer")
    return _recategorize(
        session,
        (Account.kind == "bank")
        & (Transaction.amount > 0)
        & Transaction.category_id.in_(transfer)
        & Transaction.category_source.in_(("default", "map", "provider")),
    )


def recategorize_auto(session: Session) -> int:
    """Re-run the pipeline on rows categorized only by default rules or the card company's
    category, so rule changes reach them. Never touches manual/user/seed/ai assignments."""
    return _recategorize(session, Transaction.category_source.in_(AUTO_SOURCES))


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
    session: Session,
    merchant_key: str,
    category_id: int,
    apply_to_past: bool = True,
    remember: bool = True,
) -> int:
    """Bulk: remember a user rule for the merchant (unless remember=False), then categorize its
    uncategorized txns (and, with apply_to_past, every non-manual one). Returns rows changed."""
    if remember:
        _remember(session, merchant_key, category_id)
    cond = Transaction.category_id.is_(None)
    if apply_to_past and remember:
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


def _follow_recurring(session: Session, merchant_key: str, category_id: int) -> None:
    """ "זו לא הוצאה קבועה" (moved to variable) dismisses the merchant's detected fixed item;
    "זו הוצאה קבועה" (moved to fixed) confirms it. User-defined items are left alone."""
    if not merchant_key:
        return
    group = session.scalar(select(Category.group).where(Category.id == category_id))
    item = session.scalar(
        select(RecurringItem).where(
            RecurringItem.merchant_key == merchant_key, RecurringItem.direction == "expense"
        )
    )
    if item is None or item.user_defined:
        return
    if group == "variable" and item.status != "dismissed":
        item.status = "dismissed"
    elif group == "fixed" and item.status != "confirmed":
        item.status = "confirmed"


def monthly_pattern(txns: list[tuple[date, Decimal]]) -> dict | None:
    """A charge in >= AUTO_N different months, each month's total within ±AUTO_AMOUNT of their
    median (the recurring detector's auto-confirm thresholds): likely a fixed expense."""
    by_month: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    for d, amount in txns:
        by_month[(d.year, d.month)] += abs(amount)
    if len(by_month) < AUTO_N:
        return None
    med = median(by_month.values())
    if not all(abs(a - med) <= med * AUTO_AMOUNT for a in by_month.values()):
        return None
    return {"amount": float(med), "months": len(by_month), "since": min(d for d, _ in txns)}


def uncategorized_merchants(session: Session) -> list[dict]:
    """Uncategorized transactions grouped by merchant, most frequent first; with the latest
    one's date and account as a sample, the date range, and the pattern: a monthly charge
    (monthly_pattern) or the latest installment payment (n/N)."""
    detail: dict[str, list[Transaction]] = defaultdict(list)
    for t in session.scalars(
        select(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .where(
            Transaction.category_id.is_(None),
            Transaction.merchant_key != "",
            Account.excluded.is_(False),
        )
        .order_by(Transaction.date, Transaction.id)
    ):
        detail[t.merchant_key].append(t)
    rows = session.execute(
        select(
            Transaction.merchant_key,
            func.min(Transaction.description),
            func.count(),
            func.sum(Transaction.amount),
            func.min(Account.kind),
            func.max(Transaction.date),
            func.max(Transaction.account_id),
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
    labels = account_labels(session) if rows else {}
    out = []
    for key, desc, n, total, kind, last, acct in rows:
        ts = detail[key]
        inst = [t for t in ts if (t.installment_total or 0) > 1]
        latest = inst[-1] if inst else None
        out.append(
            {
                "merchant_key": key,
                "sample_description": desc,
                "count": n,
                "total": float(total),
                "kind": "card" if kind == "card" else "bank",
                "sample_date": last,
                "account_label": labels.get(acct, ""),
                "first_date": ts[0].date,
                "installment": latest
                and {
                    "number": latest.installment_number,
                    "total": latest.installment_total,
                    "amount": float(abs(latest.amount)),
                },
                "monthly": None if inst else monthly_pattern([(t.date, t.amount) for t in ts]),
            }
        )
    return out


def category_usage(session: Session) -> list[int]:
    """Category ids by how many transactions use them, most used first."""
    return list(
        session.scalars(
            select(Transaction.category_id)
            .where(Transaction.category_id.is_not(None))
            .group_by(Transaction.category_id)
            .order_by(func.count().desc(), Transaction.category_id)
        )
    )


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
    _follow_recurring(session, txn.merchant_key, category_id)
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
