"""What a transaction counts as when money is summed by category: itself, or its split parts."""

from sqlalchemy import func, select, union_all

from freerise.models import Transaction, TransactionSplit


def txn_parts():
    """Subquery (txn_id, category_id, amount). An unsplit txn is one row as itself; a split txn
    is its parts, plus a remainder row (txn amount − parts, in the txn's own category) when the
    amount changed after splitting (e.g. a pending charge completed for a different amount)."""
    split = (
        select(
            TransactionSplit.transaction_id.label("txn_id"),
            func.sum(TransactionSplit.amount).label("total"),
        )
        .group_by(TransactionSplit.transaction_id)
        .subquery()
    )
    whole = (
        select(
            Transaction.id.label("txn_id"),
            Transaction.category_id,
            (Transaction.amount - func.coalesce(split.c.total, 0)).label("amount"),
        )
        .outerjoin(split, split.c.txn_id == Transaction.id)
        .where(split.c.txn_id.is_(None) | (Transaction.amount != split.c.total))
    )
    parts = select(
        TransactionSplit.transaction_id, TransactionSplit.category_id, TransactionSplit.amount
    )
    return union_all(whole, parts).subquery("parts")
