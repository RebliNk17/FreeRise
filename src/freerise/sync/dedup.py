import hashlib
from decimal import Decimal

from scraper.models.transaction import Transaction


def txn_key(t: Transaction) -> str:
    if t.identifier:
        # Cal's identifier is the deal number, shared by every installment of a purchase.
        if t.installments:
            return f"{t.identifier}:{t.installments.number}"
        return str(t.identifier)
    n, total = (t.installments.number, t.installments.total) if t.installments else ("", "")
    amount = Decimal(str(t.charged_amount)).quantize(Decimal("0.01"))
    return hashlib.sha1(f"{t.date}|{amount}|{t.description}|{n}/{total}".encode()).hexdigest()
