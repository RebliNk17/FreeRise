from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.cashflow.cycles import Cycle, get_start_day, prev_cycle
from freerise.cashflow.parts import txn_parts
from freerise.models import Account, Category, RecurringItem, Transaction
from freerise.view import counted

UNCATEGORIZED = "לא מסווג"
GROUPS = ("fixed", "variable", "savings", "income")
BASIS = (
    "הכנסה = סכומים חיוביים בקטגוריות הכנסה ובתנועות לא מסווגות (כולל זיכויים); "
    "זיכויים בקטגוריות הוצאה מקטינים את ההוצאה; העברות, חיוב כרטיס אשראי והתעלמות "
    "אינם נספרים; חשבונות מוחרגים אינם נספרים; תנועות ממתינות נספרות; "
    "תשלומים של עסקאות בתשלומים וחיובים חוזרים מאושרים נספרים כהוצאה קבועה (ידועים מראש)."
)


def bucket(
    group: str | None, amount, installment_total: int | None, recurring: bool = False
) -> str | None:
    """The cash-flow group a transaction (part) counts in, or None if it isn't counted.

    group: its category's group (None = uncategorized: income if positive, else variable).
    Installment payments and confirmed recurring charges (recurring=True, see
    recurring_expense_keys) are known in advance, so they count as fixed (like RiseUp), whatever
    variable category they carry (a hotel paid in 6 under תיירות, a monthly car lease under רכב)."""
    if group is None:
        group = "income" if amount > 0 else "variable"
    if group == "variable" and ((installment_total or 0) > 1 or recurring):
        return "fixed"
    return group if group in GROUPS else None


def recurring_expense_keys(session: Session) -> set[str]:
    """Merchants of confirmed recurring expenses: their charges count as fixed (bucket)."""
    return set(
        session.scalars(
            select(RecurringItem.merchant_key).where(
                RecurringItem.direction == "expense", RecurringItem.status == "confirmed"
            )
        )
    )


@dataclass
class CategoryTotal:
    category_id: int | None
    name: str
    total: Decimal
    count: int


@dataclass
class GroupSummary:
    group: str
    total: Decimal
    categories: list[CategoryTotal] = field(default_factory=list)


@dataclass
class CycleSummary:
    cycle: Cycle
    income: Decimal
    spending: Decimal
    net: Decimal
    verdict: Literal["positive", "negative"]
    groups: list[GroupSummary]
    uncategorized_total: Decimal  # sum of absolute amounts of uncategorized txns
    uncategorized_count: int
    pending_count: int
    income_fixed: Decimal = Decimal(0)  # income from non-dismissed recurring income items
    income_variable: Decimal = Decimal(0)  # income - income_fixed
    basis: str = BASIS


def cycle_summary(session: Session, cycle: Cycle) -> CycleSummary:
    p = txn_parts()  # a split txn counts as its parts
    rows = session.execute(
        select(Transaction, Category, p.c.amount)
        .join(p, p.c.txn_id == Transaction.id)
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Category, Category.id == p.c.category_id)
        .where(
            counted(),
            Transaction.effective_date >= cycle.start,
            Transaction.effective_date <= cycle.end,
        )
    ).all()
    fixed_keys = set(
        session.scalars(
            select(RecurringItem.merchant_key).where(
                RecurringItem.direction == "income", RecurringItem.status != "dismissed"
            )
        )
    )

    rec = recurring_expense_keys(session)

    # (group, category_id, name) -> [signed sum, count]
    acc: dict[tuple[str, int | None, str], list] = {}
    unc_total, unc_count, income_fixed = Decimal(0), 0, Decimal(0)
    pending: set[int] = set()
    for t, cat, amount in rows:
        if t.status == "pending":
            pending.add(t.id)
        g = bucket(cat.group if cat else None, amount, t.installment_total, t.merchant_key in rec)
        if g is None:  # transfer / card_bill / ignore
            continue
        if cat is None:
            unc_total += abs(amount)
            unc_count += 1
            key = (g, None, UNCATEGORIZED)
        else:
            key = (g, cat.id, cat.name)
        if key[0] == "income" and t.merchant_key and t.merchant_key in fixed_keys:
            income_fixed += amount
        e = acc.setdefault(key, [Decimal(0), 0])
        e[0] += amount
        e[1] += 1

    groups = []
    for g in GROUPS:
        sign = 1 if g == "income" else -1  # spending reported positive
        cats = [
            CategoryTotal(cid, name, sign * v[0], v[1])
            for (grp, cid, name), v in acc.items()
            if grp == g
        ]
        cats.sort(key=lambda c: c.total, reverse=True)
        groups.append(GroupSummary(g, sum((c.total for c in cats), Decimal(0)), cats))
    by = {g.group: g.total for g in groups}
    spending = by["fixed"] + by["variable"] + by["savings"]
    net = by["income"] - spending
    return CycleSummary(
        cycle,
        by["income"],
        spending,
        net,
        "positive" if net >= 0 else "negative",
        groups,
        unc_total,
        unc_count,
        len(pending),
        income_fixed,
        by["income"] - income_fixed,
    )


def cycle_history(session: Session, end_cycle: Cycle, n: int = 6) -> list[tuple[Cycle, Decimal]]:
    start_day = get_start_day(session)
    cycles = [end_cycle]
    for _ in range(n - 1):
        cycles.append(prev_cycle(cycles[-1], start_day))
    return [(c, cycle_summary(session, c).net) for c in reversed(cycles)]
