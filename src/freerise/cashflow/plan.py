"""Current-cycle plan: variable allowance ("left to spend"), weekly split, category budgets."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from freerise.cashflow.cycles import Cycle, cycle_for, get_start_day, prev_cycle
from freerise.cashflow.parts import txn_parts
from freerise.cashflow.savings import monthly_total, plan_statuses
from freerise.cashflow.summary import UNCATEGORIZED, CycleSummary, cycle_summary
from freerise.forecast.next_cycle import ExpectedLine, expected_in_cycle
from freerise.models import (
    Account,
    Category,
    CategoryBudget,
    CycleGoal,
    Setting,
    TrackedCategory,
    Transaction,
)
from freerise.view import counted

CENT = Decimal("0.01")
HISTORY = 6
MIN_PACE_DAYS = 7  # before this, current-cycle pace is too noisy to extrapolate
BASIS = (
    "תקציב משתנה = הכנסה צפויה (בפועל + הכנסות קבועות שטרם התקבלו) − הוצאות קבועות צפויות "
    "(בפועל + חיובים קבועים ותשלומים שטרם חויבו) − יעד סוף חודש (יעד אישי + יעדי חיסכון); "
    "שבועות א׳–ש׳, יתרת התקציב (אחרי ההוצאות בשבועות שעברו) מתחלקת לפי מספר הימים בשבוע הנוכחי ובבאים; "
    "צפי לקטגוריה = חציון 6 המחזורים הקודמים (או הסכום שקבעתם); "
    "קטגוריות במעקב שומרות לעצמן את הצפי שלהן (או מה שכבר יצא, אם יותר), "
    "והתקציב השבועי הוא מה שנשאר לשאר ההוצאות המשתנות."
)


@dataclass
class WeekPlan:
    start: date
    end: date
    spent: Decimal
    allowance: Decimal
    left: Decimal  # may be negative; UI clamps


@dataclass
class CategoryPlan:
    category_id: int | None
    name: str
    spent: Decimal
    expected: Decimal
    left: Decimal


@dataclass
class CyclePlan:
    cycle: Cycle
    expected_income: Decimal
    expected_fixed: Decimal
    goal: Decimal
    variable_allowance: Decimal
    variable_spent: Decimal
    variable_left: Decimal
    savings_spent: Decimal
    weeks: list[WeekPlan]
    categories: list[CategoryPlan]
    still_expected: list[ExpectedLine]  # fixed charges not yet seen this cycle
    savings_expected: list[ExpectedLine]  # recurring savings deposits; outside the allowance
    still_expected_income: list[ExpectedLine] = field(default_factory=list)
    basis: str = BASIS
    goal_personal: Decimal = Decimal(0)  # goal = goal_personal + goal_plans
    goal_plans: Decimal = Decimal(0)  # active savings plans' monthly amounts
    # Tracked categories keep their own expected (budget, else median); `weeks` and the rest_*
    # numbers cover only the other variable spending, so nothing is counted twice:
    # variable_allowance = Σ max(tracked expected, spent) + rest_allowance.
    tracked: list[CategoryPlan] = field(default_factory=list)
    rest_allowance: Decimal = Decimal(0)
    rest_spent: Decimal = Decimal(0)


def get_goal(session: Session, cycle: Cycle) -> Decimal:
    """This cycle's goal, else the latest earlier cycle's, else the default setting."""
    v = session.scalar(
        select(CycleGoal.amount)
        .where(CycleGoal.cycle_start <= cycle.start)
        .order_by(CycleGoal.cycle_start.desc())
        .limit(1)
    )
    if v is None:
        v = session.scalar(select(Setting.value).where(Setting.key == "month_end_goal_default"))
    return Decimal(str(v or 0))


def set_goal(session: Session, cycle: Cycle, amount: Decimal) -> None:
    row = session.scalar(select(CycleGoal).where(CycleGoal.cycle_start == cycle.start))
    if row is None:
        row = CycleGoal(cycle_start=cycle.start)
        session.add(row)
    row.amount = amount
    session.flush()


def _group(s: CycleSummary, g: str):
    return next(x for x in s.groups if x.group == g)


def tracked_ids(session: Session) -> set[int]:
    """Active tracked categories (variable group only)."""
    return set(
        session.scalars(
            select(TrackedCategory.category_id)
            .join(Category, Category.id == TrackedCategory.category_id)
            .where(TrackedCategory.active, Category.group == "variable")
        )
    )


def _variable_by_week(session: Session, cycle: Cycle, exclude: set[int]) -> dict[date, Decimal]:
    """Variable spending outside `exclude` categories (positive, net of refunds) keyed by week
    start (Sunday)."""
    p = txn_parts()
    rows = session.execute(
        select(Transaction.date, p.c.amount)
        .join(p, p.c.txn_id == Transaction.id)
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Category, Category.id == p.c.category_id)
        .where(
            counted(),
            Transaction.effective_date >= cycle.start,
            Transaction.effective_date <= cycle.end,
            # installments are fixed (summary.bucket)
            or_(Transaction.installment_total.is_(None), Transaction.installment_total <= 1),
            or_(
                (Category.group == "variable") & Category.id.not_in(exclude),
                Category.id.is_(None) & (p.c.amount < 0),
            ),
        )
    )
    out: dict[date, Decimal] = defaultdict(Decimal)
    for d, amt in rows:  # a txn attributed to this cycle sits in its first/last week
        out[_sunday(clamp(d, cycle))] -= amt
    return out


def clamp(d: date, cycle: Cycle) -> date:
    return min(max(d, cycle.start), cycle.end)


def _sunday(d: date) -> date:
    return d - timedelta(days=(d.weekday() + 1) % 7)


def week_spans(cycle: Cycle) -> list[tuple[date, date]]:
    """Sunday–Saturday weeks clipped to the cycle."""
    spans = []
    s = _sunday(cycle.start)
    while s <= cycle.end:
        spans.append((max(s, cycle.start), min(s + timedelta(days=6), cycle.end)))
        s += timedelta(days=7)
    return spans


def split_by_days(
    spans: list[tuple[date, date]],
    today: date,
    total: Decimal,
    past_spent: Decimal,
    fixed: dict[int, Decimal] | None = None,
    floor_zero: bool = False,
) -> list[Decimal]:
    """Per-week share of `total`, proportional to the days in each week.

    Past weeks (ending before today) keep their original share (total / cycle days x days).
    The current and future weeks not in `fixed` (per-week overrides, by index) share what is
    left after past spending and the fixed non-past weeks at one daily rate, so overspending
    in a past week is spread over the remaining days. Cents remainder goes to the last of
    them so they sum exactly. floor_zero: never hand out a negative share."""
    fixed = fixed or {}
    days = [(b - a).days + 1 for a, b in spans]
    rate0 = total / sum(days) if days else Decimal(0)
    remaining = total - past_spent
    out: list[Decimal] = []
    free: list[int] = []
    for i, ((_, b), d) in enumerate(zip(spans, days, strict=True)):
        if i in fixed:
            out.append(fixed[i])
            if b >= today:
                remaining -= fixed[i]
        elif b < today:
            out.append((rate0 * d).quantize(CENT))
        else:
            out.append(Decimal(0))
            free.append(i)
    if floor_zero and remaining < 0:
        remaining = Decimal(0)
    free_days = sum(days[i] for i in free)
    for i in free:
        out[i] = (remaining * days[i] / free_days).quantize(CENT)
    if free:
        out[free[-1]] += remaining - sum((out[i] for i in free), Decimal(0))
    return out


def _weeks(cycle: Cycle, today: date, by_week: dict, allowance: Decimal) -> list[WeekPlan]:
    """Past weeks: planned share, left 0. Current/future: daily-rate share of what is left."""
    spans = week_spans(cycle)
    spent = [by_week[_sunday(a)] for a, _ in spans]
    past_spent = sum((x for (_, b), x in zip(spans, spent, strict=True) if b < today), Decimal(0))
    shares = split_by_days(spans, today, allowance, past_spent)
    return [
        WeekPlan(a, b, x, al, Decimal(0) if b < today else al - x)
        for (a, b), x, al in zip(spans, spent, shares, strict=True)
    ]


def history(session: Session, cycle: Cycle, n: int = HISTORY) -> list[CycleSummary]:
    """Last n complete cycles before `cycle` that have any data (empty pre-history skipped)."""
    start_day = get_start_day(session)
    out, c = [], cycle
    for _ in range(n):
        c = prev_cycle(c, start_day)
        s = cycle_summary(session, c)
        if s.income or s.spending:
            out.append(s)
    return out


def projected_month_end(p: CyclePlan, today: date, hist: list[CycleSummary]) -> Decimal:
    """expected income − expected fixed − variable spent − variable still to come.

    Still to come is at this cycle's pace; in its first MIN_PACE_DAYS days, at the median
    past cycle's daily variable spending (when there is history)."""
    days = (p.cycle.end - p.cycle.start).days + 1
    elapsed = min(days, max(1, (today - p.cycle.start).days + 1))
    if elapsed >= MIN_PACE_DAYS or not hist:
        per_day = p.variable_spent / elapsed
    else:
        per_day = median(_group(s, "variable").total for s in hist) / days
    rest = days - elapsed
    return p.expected_income - p.expected_fixed - p.variable_spent - per_day * rest


def _variable_cats(s: CycleSummary) -> dict[int | None, tuple[str, Decimal]]:
    return {c.category_id: (c.name, c.total) for c in _group(s, "variable").categories}


def cycle_plan(session: Session, today: date) -> CyclePlan:
    start_day = get_start_day(session)
    cycle = cycle_for(today, start_day)
    cur = cycle_summary(session, cycle)
    ec = expected_in_cycle(session, cycle, today)
    pending_income = [x for x in ec.income_items if not x.charged]
    pending_fixed = [x for x in ec.fixed_items if not x.charged]
    expected_income = cur.income + sum((x.amount for x in pending_income), Decimal(0))
    expected_fixed = _group(cur, "fixed").total + sum((x.amount for x in pending_fixed), Decimal(0))
    personal = get_goal(session, cycle)
    plans = monthly_total(plan_statuses(session, cycle, start_day))
    goal = personal + plans
    allowance = expected_income - expected_fixed - goal
    spent = _group(cur, "variable").total

    hist = history(session, cycle)

    now = _variable_cats(cur)
    past = [_variable_cats(s) for s in hist]
    names = {cid: v[0] for d in [*past, now] for cid, v in d.items()}
    cats = []
    for cid, name in names.items():
        exp = median(d.get(cid, ("", Decimal(0)))[1] for d in past) if past else Decimal(0)
        sp = now.get(cid, (name, Decimal(0)))[1]
        cats.append(CategoryPlan(cid, name or UNCATEGORIZED, sp, exp, exp - sp))
    cats.sort(key=lambda x: (x.spent, x.expected), reverse=True)

    ids = tracked_ids(session)
    budgets = dict(
        session.execute(
            select(CategoryBudget.category_id, CategoryBudget.amount).where(
                CategoryBudget.cycle_start == cycle.start, CategoryBudget.category_id.in_(ids)
            )
        ).all()
    )
    by_id = {c.category_id: c for c in cats}
    tracked = []
    for cid in sorted(ids):
        c = by_id.get(cid)
        sp = c.spent if c else Decimal(0)
        exp = budgets.get(cid, Decimal(c.expected).quantize(CENT) if c else Decimal(0))
        tracked.append(CategoryPlan(cid, c.name if c else "", sp, exp, exp - sp))
    reserved = sum((max(c.expected, c.spent) for c in tracked), Decimal(0))
    rest_allowance = allowance - reserved
    rest_spent = spent - sum((c.spent for c in tracked), Decimal(0))

    return CyclePlan(
        cycle,
        expected_income,
        expected_fixed,
        goal,
        allowance,
        spent,
        allowance - spent,
        _group(cur, "savings").total,
        _weeks(cycle, today, _variable_by_week(session, cycle, ids), rest_allowance),
        cats,
        pending_fixed,
        ec.savings_items,
        pending_income,
        goal_personal=personal,
        goal_plans=plans,
        tracked=tracked,
        rest_allowance=rest_allowance,
        rest_spent=rest_spent,
    )
