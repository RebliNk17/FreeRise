"""Home screen for one cycle: variable/tracked/fixed/savings/income cards. API contract: web/lib/home.ts.

Money is positive for spent/expected/left (left may go negative), signed on transactions.
Past cycles: there is no plan to compare with, so expected = spent everywhere (allowance,
tracked categories unless overridden, fixed, savings, income) and summary is None."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from freerise.accounts import account_holders, account_labels
from freerise.cashflow.cycles import (
    Cycle,
    cycle_for,
    cycle_shift,
    get_start_day,
    next_cycle,
    prev_cycle,
)
from freerise.cashflow.parts import txn_parts
from freerise.cashflow.plan import CENT, HISTORY, clamp, cycle_plan, split_by_days, week_spans
from freerise.cashflow.savings import monthly_total, plan_statuses
from freerise.cashflow.summary import GROUPS, UNCATEGORIZED
from freerise.forecast.next_cycle import ExpectedLine, expected_in_cycle
from freerise.models import (
    Account,
    Category,
    CategoryBudget,
    CategoryWeekBudget,
    RecurringItem,
    Setting,
    TrackedCategory,
    Transaction,
    TransactionSplit,
)
from freerise.view import counted

OVERDUE_DAYS = 3
WEEKLY_DEFAULT = ("כלכלה",)  # supermarket is tracked weekly by default
MIN_ACTIVE_CYCLES = 2  # default tracking: spent in >= this many of the last HISTORY cycles
ZERO = Decimal(0)


@dataclass
class YM:
    year: int
    month: int


@dataclass
class CycleInfo:
    start: date
    end: date
    label_year: int
    label_month: int
    is_current: bool
    prev: YM
    next: YM | None


@dataclass
class Summary:
    week_left: Decimal
    next_week_allowance: Decimal
    goal: Decimal
    goal_personal: Decimal
    goal_plans: Decimal
    variable_allowance: Decimal


@dataclass
class SplitPart:
    category_id: int
    category_name: str
    amount: Decimal


@dataclass
class Txn:
    """A split transaction shows up once per part: amount and category are the part's;
    split_total is the whole transaction and split lists all parts."""

    id: int
    date: date
    amount: Decimal
    description: str
    merchant_key: str
    category_id: int | None
    category_name: str | None
    group: str | None
    account_id: int
    account_label: str
    note: str | None
    installment_number: int | None
    installment_total: int | None
    status: str
    account_holder: str = ""
    cycle_shift: str | None = None  # previous|next: attributed to a neighbour cycle
    cycle_label: str | None = None  # that cycle, e.g. "ספטמבר 2026"
    fixed_income_id: int | None = None  # confirmed income item of this merchant
    cycle_date_source: str | None = None  # auto|manual
    split_total: Decimal | None = None
    split: list[SplitPart] | None = None


@dataclass
class Week:
    index: int
    start: date
    end: date
    spent: Decimal
    left: Decimal
    expected: Decimal | None
    is_current: bool
    is_past: bool
    transactions: list[Txn]


@dataclass
class Variable:
    spent: Decimal
    allowance: Decimal
    weeks: list[Week]


@dataclass
class HistoryPoint:
    label_year: int
    label_month: int
    spent: Decimal


@dataclass
class TrackedOut:
    category_id: int
    name: str
    spent: Decimal
    expected: Decimal
    expected_overridden: bool
    left: Decimal
    mode: str
    weeks: list[Week] | None
    transactions: list[Txn]
    history: list[HistoryPoint]


@dataclass
class CategoryRef:
    category_id: int
    name: str


@dataclass
class Savings:
    spent: Decimal
    expected: Decimal
    transactions: list[Txn]


@dataclass
class FixedItem:
    label: str
    account_label: str | None
    expected_date: date | None
    expected_amount: Decimal
    actual_amount: Decimal
    status: str  # charged | expected | overdue
    transactions: list[Txn]
    recurring_id: int | None


@dataclass
class FixedGroup:
    category_id: int | None
    name: str
    spent: Decimal
    expected: Decimal
    items: list[FixedItem]


@dataclass
class Fixed:
    spent: Decimal
    expected: Decimal
    groups: list[FixedGroup]


@dataclass
class Total:
    spent: Decimal
    expected: Decimal


@dataclass
class VariableIncome:
    received: Decimal
    transactions: list[Txn]


@dataclass
class Income:
    received: Decimal
    expected: Decimal
    fixed_groups: list[FixedGroup]
    variable: VariableIncome


@dataclass
class MovedNext:
    transactions: list[Txn]


@dataclass
class Home:
    cycle: CycleInfo
    summary: Summary | None
    variable: Variable
    tracked: list[TrackedOut]
    untracked_available: list[CategoryRef]
    savings: Savings
    fixed: Fixed
    total: Total
    income: Income
    multi_holder: bool = False  # accounts belong to more than one person
    moved_next: MovedNext | None = None  # current cycle only


def _ym(c: Cycle) -> YM:
    return YM(c.label_month.year, c.label_month.month)


def _sum(txns: list[Txn], sign: int = -1) -> Decimal:
    return sum((sign * t.amount for t in txns), ZERO)


def _weeks(
    cycle: Cycle, today: date, txns: list[Txn], total: Decimal, overrides: dict[int, Decimal]
) -> list[Week]:
    """Split `total` by days (split_by_days; overridden weeks first, never negative). Past
    weeks show their planned share with left 0."""
    spans = week_spans(cycle)
    weeks = []
    for i, (a, b) in enumerate(spans):
        # a txn attributed to this cycle from a neighbour sits in its first/last week
        ts = [t for t in txns if a <= clamp(t.date, cycle) <= b]
        weeks.append(Week(i, a, b, _sum(ts), ZERO, None, a <= today <= b, b < today, ts))
    past_spent = sum((w.spent for w in weeks if w.is_past), ZERO)
    shares = split_by_days(spans, today, total, past_spent, overrides, floor_zero=True)
    for w, x in zip(weeks, shares, strict=True):
        w.expected = x
        w.left = ZERO if w.is_past else x - w.spent
    return weeks


def _status(line: ExpectedLine, today: date) -> str:
    if line.charged:
        return "charged"
    return "overdue" if line.date < today - timedelta(days=OVERDUE_DAYS) else "expected"


def _groups(
    lines: list[ExpectedLine],
    pool: list[Txn],
    cats: dict[int, Category],
    today: date,
    current: bool,
    sign: int,
) -> list[FixedGroup]:
    """Items = expected lines (with the pool txns they matched) + unmatched pool txns per
    merchant; grouped by category. Group expected = spent + not-yet-charged expectations."""
    by_id = {t.id: t for t in pool}
    claimed: set[int] = set()
    items: dict[int | None, list[tuple[FixedItem, Decimal]]] = defaultdict(list)
    for ln in lines:
        ts = [by_id[i] for i in ln.txn_ids if i in by_id and i not in claimed]
        # ponytail: a charged line whose txns sit in another group (e.g. installments at a
        # variable-category store) is counted there, not here.
        if (ln.charged and not ts) or (not ln.charged and not current):
            continue
        claimed.update(t.id for t in ts)
        actual = _sum(ts, sign)
        exp = (ln.expected_amount or ln.amount) if current else actual
        item = FixedItem(
            ln.label,
            ln.account_label or (ts[-1].account_label if ts else None),
            ln.date,
            exp,
            actual,
            _status(ln, today),
            ts,
            ln.recurring_id,
        )
        cid = ts[0].category_id if ts else ln.category_id
        items[cid].append((item, ZERO if ln.charged else exp))
    rest: dict[tuple, list[Txn]] = defaultdict(list)
    for t in pool:
        if t.id not in claimed:
            rest[(t.category_id, t.merchant_key or t.description)].append(t)
    for (cid, _), ts in rest.items():
        actual = _sum(ts, sign)
        items[cid].append(
            (
                FixedItem(
                    ts[0].description,
                    ts[0].account_label,
                    None,
                    actual,
                    actual,
                    "charged",
                    ts,
                    None,
                ),
                ZERO,
            )
        )
    out = []
    for cid, its in items.items():
        spent = sum((i.actual_amount for i, _ in its), ZERO)
        its.sort(key=lambda x: x[0].expected_date or x[0].transactions[-1].date)
        out.append(
            FixedGroup(
                cid,
                cats[cid].name if cid in cats else UNCATEGORIZED,
                spent,
                spent + sum((p for _, p in its), ZERO),
                [i for i, _ in its],
            )
        )
    out.sort(key=lambda g: g.expected, reverse=True)
    return out


def _history(
    session: Session, cycles: list[Cycle], start_day: int
) -> tuple[list[dict[int, Decimal]], list[bool]]:
    """Per past cycle: variable spending by category, and whether the cycle has any data."""
    idx = {c.start: i for i, c in enumerate(cycles)}
    var: list[dict[int, Decimal]] = [defaultdict(Decimal) for _ in cycles]
    has = [False] * len(cycles)
    p = txn_parts()
    rows = session.execute(
        select(
            Transaction.effective_date,
            p.c.category_id,
            Category.group,
            func.sum(p.c.amount),
        )
        .join(p, p.c.txn_id == Transaction.id)
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Category, Category.id == p.c.category_id)
        .where(
            counted(),
            Transaction.effective_date >= cycles[0].start,
            Transaction.effective_date <= cycles[-1].end,
            or_(Category.id.is_(None), Category.group.in_(GROUPS)),
        )
        .group_by(Transaction.effective_date, p.c.category_id, Category.group)
    )
    for d, cid, group, total in rows:
        i = idx[cycle_for(d, start_day).start]
        has[i] = True
        if group == "variable":
            var[i][cid] -= total
    return var, has


def _seed_tracking(
    session: Session, var_cats: dict[int, Category], hist: list[dict], expected: dict
) -> None:
    """Default: variable categories with spending in >= MIN_ACTIVE_CYCLES past cycles and a
    non-zero expected (median) — a card that would show 0 of 0 is noise."""
    picked = [
        cid
        for cid in var_cats
        if sum(h.get(cid, ZERO) > 0 for h in hist) >= MIN_ACTIVE_CYCLES
        and expected.get(cid, ZERO) > 0
    ]
    picked.sort(key=lambda cid: expected.get(cid, ZERO), reverse=True)
    for n, cid in enumerate(picked):
        session.add(
            TrackedCategory(
                category_id=cid,
                mode=default_mode(var_cats[cid].name),
                sort_order=n,
                active=True,
            )
        )
    session.flush()


def split_parts(session: Session, cats: dict[int, Category]) -> dict[int, list[SplitPart]]:
    """txn id -> its parts, for every split transaction."""
    out: dict[int, list[SplitPart]] = defaultdict(list)
    for r in session.scalars(select(TransactionSplit).order_by(TransactionSplit.id)):
        name = cats[r.category_id].name if r.category_id in cats else UNCATEGORIZED
        out[r.transaction_id].append(SplitPart(r.category_id, name, r.amount))
    return out


MANUAL_ORDER = "tracked_order_manual"


def manual_order(session: Session) -> bool:
    return bool(session.scalar(select(Setting.value).where(Setting.key == MANUAL_ORDER)))


def default_mode(name: str) -> str:
    return "weekly" if name in WEEKLY_DEFAULT else "monthly"


def build_home(session: Session, cycle: Cycle, today: date) -> Home:
    """May seed tracked_categories (flush only; caller commits)."""
    start_day = get_start_day(session)
    current = cycle.start <= today <= cycle.end
    nxt = next_cycle(cycle, start_day)
    info = CycleInfo(
        cycle.start,
        cycle.end,
        cycle.label_month.year,
        cycle.label_month.month,
        current,
        _ym(prev_cycle(cycle, start_day)),
        _ym(nxt) if nxt.start <= today else None,
    )
    cats = {c.id: c for c in session.scalars(select(Category))}
    labels, holders = account_labels(session), account_holders(session)
    income_items = session.execute(
        select(RecurringItem.merchant_key, RecurringItem.id, RecurringItem.status).where(
            RecurringItem.direction == "income", RecurringItem.status != "dismissed"
        )
    ).all()
    fixed_keys = {k for k, _, _ in income_items}
    confirmed = {k: i for k, i, st in income_items if st == "confirmed"}

    splits = split_parts(session, cats)
    parts = txn_parts()

    def rows(*where) -> list[tuple[str, Txn]]:
        out = []
        for t, cid, amount in session.execute(
            select(Transaction, parts.c.category_id, parts.c.amount)
            .join(parts, parts.c.txn_id == Transaction.id)
            .join(Account, Account.id == Transaction.account_id)
            .where(counted(), *where)
            .order_by(Transaction.date.desc(), Transaction.id.desc(), parts.c.category_id)
        ):
            cat = cats.get(cid)
            if cat is None:
                group = "income" if amount > 0 else "variable"
            elif cat.group in GROUPS:
                group = cat.group
            else:  # transfer / card_bill / ignore
                continue
            out.append(
                (
                    group,
                    Txn(
                        t.id,
                        t.date,
                        amount,
                        t.description,
                        t.merchant_key,
                        cid,
                        cat.name if cat else None,
                        cat.group if cat else None,
                        t.account_id,
                        labels.get(t.account_id, ""),
                        t.note,
                        t.installment_number,
                        t.installment_total,
                        t.status,
                        holders.get(t.account_id, ""),
                        *cycle_shift(t.date, t.cycle_date, start_day),
                        confirmed.get(t.merchant_key) if t.amount > 0 else None,
                        t.cycle_date_source,
                        t.amount if t.id in splits else None,
                        splits.get(t.id),
                    ),
                )
            )
        return out

    buckets: dict[str, list[Txn]] = defaultdict(list)
    for group, txn in rows(
        Transaction.effective_date >= cycle.start, Transaction.effective_date <= cycle.end
    ):
        buckets[group].append(txn)
    # Happened this cycle but attributed to a cycle home can't navigate to yet: listed here
    # so the move stays undoable.
    moved = []
    if info.next is None:
        moved = [
            t
            for _, t in rows(
                Transaction.date >= cycle.start,
                Transaction.date <= cycle.end,
                Transaction.effective_date > cycle.end,
            )
        ]

    hist_cycles = [prev_cycle(cycle, start_day)]
    for _ in range(HISTORY - 1):
        hist_cycles.append(prev_cycle(hist_cycles[-1], start_day))
    hist_cycles.reverse()
    hist, has = _history(session, hist_cycles, start_day)
    with_data = [h for h, ok in zip(hist, has, strict=True) if ok]
    var_cats = {cid: c for cid, c in cats.items() if c.group == "variable"}
    medians = {
        cid: Decimal(median(h.get(cid, ZERO) for h in with_data)).quantize(CENT)
        for cid in var_cats
        if with_data
    }

    if not session.scalar(select(func.count()).select_from(TrackedCategory)):
        _seed_tracking(session, var_cats, hist, medians)
    tracked_rows = [
        r
        for r in session.scalars(select(TrackedCategory))
        if r.active and r.category_id in var_cats
    ]
    budgets = dict(
        session.execute(
            select(CategoryBudget.category_id, CategoryBudget.amount).where(
                CategoryBudget.cycle_start == cycle.start
            )
        ).all()
    )
    week_budgets: dict[int, dict[int, Decimal]] = defaultdict(dict)
    for cid, i, amt in session.execute(
        select(
            CategoryWeekBudget.category_id, CategoryWeekBudget.week_index, CategoryWeekBudget.amount
        ).where(CategoryWeekBudget.cycle_start == cycle.start)
    ):
        week_budgets[cid][i] = amt

    var_txns = buckets["variable"]
    plan = cycle_plan(session, today) if current else None
    ec = expected_in_cycle(session, cycle, today)

    # Variable card
    var_spent = _sum(var_txns)
    allowance = plan.variable_allowance if plan else var_spent
    vweeks = _weeks(cycle, today, var_txns, allowance, {})
    summary = None
    if plan:
        for w, pw in zip(vweeks, plan.weeks, strict=True):  # same rule; plan's numbers win
            w.expected, w.left = pw.allowance, pw.left
        cur = next((w for w in vweeks if w.is_current), vweeks[-1])
        after = vweeks[cur.index + 1] if cur.index + 1 < len(vweeks) else None
        summary = Summary(
            cur.left,
            after.expected if after else ZERO,
            plan.goal,
            plan.goal_personal,
            plan.goal_plans,
            plan.variable_allowance,
        )

    # Tracked categories
    tracked = []
    for r in tracked_rows:
        ts = [t for t in var_txns if t.category_id == r.category_id]
        spent = _sum(ts)
        overridden = r.category_id in budgets
        if overridden:
            expected = budgets[r.category_id]
        else:
            expected = medians.get(r.category_id, ZERO) if current else spent
        tracked.append(
            TrackedOut(
                r.category_id,
                var_cats[r.category_id].name,
                spent,
                expected,
                overridden,
                expected - spent,
                r.mode,
                _weeks(cycle, today, ts, expected, week_budgets[r.category_id])
                if r.mode == "weekly"
                else None,
                ts,
                [
                    HistoryPoint(
                        c.label_month.year, c.label_month.month, h.get(r.category_id, ZERO)
                    )
                    for c, h in zip(hist_cycles, hist, strict=True)
                ],
            )
        )
    order = {r.category_id: r.sort_order for r in tracked_rows}
    if manual_order(session):  # the user's own order (settings), else biggest first
        tracked.sort(key=lambda x: order[x.category_id])
    else:
        tracked.sort(key=lambda x: (-x.expected, order[x.category_id]))
    active = {r.category_id for r in tracked_rows}
    untracked = [
        CategoryRef(c.id, c.name)
        for c in sorted(var_cats.values(), key=lambda c: (c.sort_order, c.name))
        if c.id not in active
    ]

    # Savings
    sav_txns = buckets["savings"]
    sav_spent = _sum(sav_txns)
    sav_expected = sav_spent
    if current:
        sav_expected = monthly_total(plan_statuses(session, cycle, start_day)) + sum(
            (x.amount for x in ec.savings_items), ZERO
        )

    # Fixed
    fgroups = _groups(ec.fixed_items, buckets["fixed"], cats, today, current, -1)
    fixed = Fixed(
        sum((g.spent for g in fgroups), ZERO), sum((g.expected for g in fgroups), ZERO), fgroups
    )

    # Income: recurring (non-dismissed) streams are fixed, the rest variable — as cycle_summary
    inc = buckets["income"]
    igroups = _groups(
        ec.income_items, [t for t in inc if t.merchant_key in fixed_keys], cats, today, current, 1
    )
    ivar = [t for t in inc if t.merchant_key not in fixed_keys]
    ivar_total = _sum(ivar, 1)
    income = Income(
        sum((g.spent for g in igroups), ZERO) + ivar_total,
        sum((g.expected for g in igroups), ZERO) + ivar_total,
        igroups,
        VariableIncome(ivar_total, ivar),
    )

    return Home(
        info,
        summary,
        Variable(var_spent, allowance, vweeks),
        tracked,
        untracked,
        Savings(sav_spent, sav_expected, sav_txns),
        fixed,
        Total(fixed.spent + var_spent + sav_spent, fixed.expected + allowance + sav_expected),
        income,
        len(set(holders.values())) > 1,
        MovedNext(moved),
    )
