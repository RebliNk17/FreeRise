"""Insights: small independent checks over the cycle plan and history, shown as cards on home."""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import cached_property
from statistics import median, quantiles
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from freerise.cashflow.balances import Balances, balances
from freerise.cashflow.cycles import Cycle, cycle_for, get_start_day
from freerise.cashflow.fees import fees_in_cycle
from freerise.cashflow.parts import txn_parts
from freerise.cashflow.plan import (
    MIN_PACE_DAYS,
    CyclePlan,
    cycle_plan,
    history,
    projected_month_end,
)
from freerise.cashflow.summary import UNCATEGORIZED, CycleSummary
from freerise.models import (
    Account,
    Category,
    CycleGoal,
    InsightState,
    RecurringItem,
    Transaction,
)
from freerise.reconcile.card_bills import reconcile_link, reconcile_range
from freerise.view import counted

log = logging.getLogger("freerise.insights")
SNOOZE_DAYS = 7
OVERDUE_DAYS = 3  # as home's "לא ירד עדיין"
PRUNE_DAYS = 120  # insight states untouched this long are forgotten
CAP = 6
DISPLAY = {"כלכלה": "סופר"}  # same as web CATEGORY_DISPLAY
Severity = Literal["info", "warning", "positive"]
ORDER = {"warning": 0, "positive": 1, "info": 2}


@dataclass
class Insight:
    key: str  # stable id; per-cycle insights include the cycle start, standing ones don't
    kind: str
    severity: Severity
    title: str
    body: str
    action_label: str | None = None
    link: str | None = None
    amount: Decimal | None = None
    # Extra buttons the card runs in place: {"label", "method", "path"} (API path under /api).
    actions: list[dict] | None = None


def ils(x) -> str:
    return f"₪{Decimal(x):,.0f}"


def group_total(s: CycleSummary, g: str) -> Decimal:
    return next(x.total for x in s.groups if x.group == g)


@dataclass
class Ctx:
    session: Session
    today: date
    cycle: Cycle

    @cached_property
    def hist(self) -> list[CycleSummary]:
        return history(self.session, self.cycle)

    @cached_property
    def plan(self) -> CyclePlan:
        return cycle_plan(self.session, self.today)

    @cached_property
    def balances(self) -> Balances:
        return balances(self.session, self.cycle)

    @property
    def days(self) -> int:
        return (self.cycle.end - self.cycle.start).days + 1

    @property
    def elapsed(self) -> int:
        return (self.today - self.cycle.start).days + 1

    @property
    def cashflow_link(self) -> str:
        m = self.cycle.label_month
        return f"/home/{m.year}/{m.month}"

    @cached_property
    def projected_end(self) -> Decimal:
        return projected_month_end(self.plan, self.today, self.hist)


def negative_cycle(ctx: Ctx) -> list[Insight]:
    end = ctx.projected_end
    if end >= 0:
        return []
    return [
        Insight(
            f"negative_cycle:{ctx.cycle.start}",
            "negative_cycle",
            "warning",
            "החודש עלול להיגמר במינוס",
            f"אם ההוצאות ימשיכו בקצב הנוכחי, בסוף החודש יחסרו בערך {ils(-end)}. "
            "האטה קטנה בהוצאות המשתנות יכולה לסגור את הפער.",
            "לתחזית",
            "/forecast",
            -end,
        )
    ]


def low_balance_before_income(ctx: Ctx) -> list[Insight]:
    b = ctx.balances
    if b.bank_total is None:
        return []
    bal, p = b.bank_total, ctx.plan
    # ponytail: no pending income this cycle -> count charges up to the cycle end
    pay = min((x.date for x in p.still_expected_income), default=ctx.cycle.end + timedelta(1))
    pay = max(pay, ctx.today)  # late income: it's still "next"
    banks = {a.id for a, _, _ in b.banks}
    # Card lines (installments) are already inside the upcoming card charges.
    fixed = sum(
        (x.amount for x in p.still_expected if x.date < pay and x.account_id in banks),
        Decimal(0),
    )
    due = fixed + b.upcoming_card_charges
    left = bal - due
    if left >= 0:
        return []
    return [
        Insight(
            f"low_balance_before_income:{ctx.cycle.start}",
            "low_balance_before_income",
            "warning",
            "העו״ש עלול לרדת מתחת לאפס",
            f"עד ההכנסה הבאה ({pay:%d.%m}) צפויים חיובים של {ils(due)} "
            "(כולל חיובי האשראי הקרובים), "
            f"ובעו״ש יש עכשיו {ils(bal)}. כדאי לדאוג לכיסוי לפני כן.",
            "לחיובים הצפויים",
            "/forecast",
            -left,
        )
    ]


def idle_cash(ctx: Ctx) -> list[Insight]:
    bal = ctx.balances.bank_total
    if bal is None or not ctx.hist:
        return []
    cushion = 2 * median(group_total(s, "fixed") + group_total(s, "variable") for s in ctx.hist)
    extra = (bal - cushion) // 500 * 500
    if cushion <= 0 or extra < 500:
        return []
    return [
        Insight(
            f"idle_cash:{extra // 5000}",  # same bucket -> stays dismissed
            "idle_cash",
            "positive",
            "יש בעו״ש כסף שלא עובד",
            f"בעו״ש {ils(bal)}, יותר מפי שניים מההוצאות בחודש רגיל. "
            f"אפשר להעביר בערך {ils(extra)} לחיסכון או לפיקדון ועדיין להשאיר כרית נוחה.",
            amount=Decimal(extra),
        )
    ]


def no_goal(ctx: Ctx) -> list[Insight]:
    has = ctx.session.scalar(select(CycleGoal.id).where(CycleGoal.cycle_start == ctx.cycle.start))
    if has or ctx.elapsed > 10:
        return []
    goal = ctx.plan.goal_personal
    carried = f" בינתיים ממשיך היעד הקודם, {ils(goal)}." if goal > 0 else ""
    return [
        Insight(
            f"no_goal:{ctx.cycle.start}",
            "no_goal",
            "info",
            "עוד לא קבעתם יעד לחודש הזה",
            "יעד לסוף החודש עוזר לדעת כמה אפשר להוציא בכל שבוע." + carried,
            "לקביעת יעד",
            "/home#goal",
        )
    ]


def goal_status(ctx: Ctx) -> list[Insight]:
    goal = ctx.plan.goal
    if goal <= 0:
        return []
    end = ctx.projected_end
    if end >= goal:
        return [
            Insight(
                f"goal_on_track:{ctx.cycle.start}",
                "goal_on_track",
                "positive",
                "בדרך ליעד",
                f"בקצב הנוכחי החודש ייסגר עם כ-{ils(end)}, מעל היעד של {ils(goal)}.",
                amount=end - goal,
            )
        ]
    if end < 0:
        return []  # negative_cycle says it
    return [
        Insight(
            f"goal_at_risk:{ctx.cycle.start}",
            "goal_at_risk",
            "warning",
            "היעד החודשי בסכנה",
            f"בקצב הנוכחי יחסרו כ-{ils(goal - end)} כדי להגיע ליעד של {ils(goal)}.",
            "לתקציב השבועי",
            "/home",
            goal - end,
        )
    ]


def category_trend(ctx: Ctx) -> list[Insight]:
    if ctx.elapsed < MIN_PACE_DAYS:
        return []
    frac = Decimal(ctx.elapsed) / ctx.days
    ups, downs = [], []
    for c in ctx.plan.categories:
        if c.expected <= 0:
            continue
        pace = c.spent / frac
        name = DISPLAY.get(c.name, c.name or UNCATEGORIZED)
        if pace >= c.expected * Decimal("1.3") and pace - c.expected >= 200:
            ups.append((pace - c.expected, c, pace, name))
        # ponytail: lumpy categories look "down" early in the cycle; wait for half of it
        elif (
            frac >= Decimal("0.5")
            and pace <= c.expected * Decimal("0.8")
            and c.expected - pace >= 200
        ):
            downs.append((c.expected - pace, c, pace, name))
    out = []
    for diff, c, pace, name in sorted(ups, key=lambda x: x[0], reverse=True)[:2]:
        out.append(
            Insight(
                f"category_up:{ctx.cycle.start}:{c.category_id}",
                "category_up",
                "warning",
                f"{name}: יותר מהרגיל",
                f"בקצב הזה {name} יגיע החודש לכ-{ils(pace)}, לעומת {ils(c.expected)} בחודש רגיל.",
                "לתזרים",
                ctx.cashflow_link,
                diff,
            )
        )
    for diff, c, _pace, name in sorted(downs, key=lambda x: x[0], reverse=True)[:2]:
        out.append(
            Insight(
                f"category_down:{ctx.cycle.start}:{c.category_id}",
                "category_down",
                "positive",
                f"{name}: פחות מהרגיל",
                f"על {name} יצא החודש בערך {1 - (c.spent / frac) / c.expected:.0%} "
                "פחות מבחודש רגיל. כל הכבוד!",
                amount=diff,
            )
        )
    return out


def saving_capacity(ctx: Ctx) -> list[Insight]:
    pos = [s.net for s in ctx.hist if s.net > 0]
    if not ctx.hist or median(s.net for s in ctx.hist) <= 0:
        return []
    x = quantiles(pos, n=4, method="inclusive")[0] if len(pos) > 1 else pos[0]
    goal = ctx.plan.goal
    extra = Decimal(x) - goal  # beyond what the goal already sets aside
    if extra <= 0:
        return []
    more = f", מעבר ליעד של {ils(goal)}" if goal > 0 else ""
    return [
        Insight(
            f"saving_capacity:{extra // 500 * 500:.0f}",  # same bucket -> stays dismissed
            "saving_capacity",
            "positive",
            "יש לכם מקום לחסוך",
            f"גם בחודשים החלשים של חצי השנה האחרונה נשארו לפחות {ils(x)}. "
            f"אתם יכולים להעביר עוד {ils(extra)} לחיסכון כבר בתחילת כל חודש{more}.",
            amount=extra,
        )
    ]


def fixed_heavy(ctx: Ctx) -> list[Insight]:
    if not ctx.hist:
        return []
    inc = median(s.income for s in ctx.hist)
    fixed = median(group_total(s, "fixed") for s in ctx.hist)
    if inc <= 0 or fixed / inc <= Decimal("0.6"):
        return []
    return [
        Insight(
            f"fixed_heavy:{round(fixed / inc * 20) * 5}",  # ratio to 5% -> stays dismissed
            "fixed_heavy",
            "warning",
            "הקבועות לוקחות את רוב ההכנסה",
            f"בערך {fixed / inc:.0%} מההכנסה החודשית הולכים להוצאות קבועות. "
            "שווה לעבור על המנויים וההלוואות ולבדוק מה אפשר להוריד.",
            amount=fixed,
        )
    ]


def fees(ctx: Ctx) -> list[Insight]:
    f = fees_in_cycle(ctx.session, ctx.cycle)
    if f.total <= 0:
        return []
    return [
        Insight(
            f"fees:{ctx.cycle.start}",
            "fees",
            "warning",
            "החודש יצא כסף על עמלות",
            f"עד עכשיו שולמו {ils(f.total)} עמלות. "
            "לפעמים שיחה קצרה עם הבנק או חברת האשראי מספיקה כדי לבטל אותן.",
            "לפירוט",
            ctx.cashflow_link,
            f.total,
        )
    ]


def unknown_card(ctx: Ctx) -> list[Insight]:
    bills = [
        b
        for b in reconcile_range(ctx.session, ctx.today - timedelta(days=45), ctx.today)
        if b.status == "unknown_card"
    ]
    if not bills:
        return []
    total = sum((b.amount for b in bills), Decimal(0))
    latest = max(bills, key=lambda b: b.date)
    return [
        Insight(
            f"unknown_card:{max(b.bank_txn_id for b in bills)}",  # a new bill shows it again
            "unknown_card",
            "warning",
            "חיובי אשראי בלי פירוט",
            f"בחודש וחצי האחרונים ירדו מהבנק {ils(total)} לכרטיסים שלא מחוברים ל-FreeRise, "
            "ולכן לא רואים על מה הכסף יצא.",
            "להתאמת חיובים",
            reconcile_link(ctx.session, latest.date),
            total,
        )
    ]


def variable_income_expected(ctx: Ctx) -> list[Insight]:
    items = ctx.session.scalars(
        select(RecurringItem).where(
            RecurringItem.direction == "income",
            RecurringItem.status == "confirmed",
            RecurringItem.amount_kind == "variable",
        )
    ).all()
    if not items:
        return []
    total = sum((i.expected_amount for i in items), Decimal(0))
    names = ", ".join(i.label for i in items)
    return [
        Insight(
            "variable_income_expected:" + ",".join(map(str, sorted(i.id for i in items))),
            "variable_income_expected",
            "info",
            "הכנסה שמשתנה מחודש לחודש",
            f"ההכנסה מהמקורות: {names} משתנה מחודש לחודש, "
            f"ולכן בחישובים לקחנו הערכה זהירה של {ils(total)}.",
            amount=total,
        )
    ]


EATING_OUT = "אוכל בחוץ"
WEEKEND = (4, 5)  # Friday, Saturday (date.weekday())
RATIO = Decimal("1.5")


def eating_out_weekend(ctx: Ctx) -> list[Insight]:
    """Eating out per day on weekends vs. weekdays over the last 3 complete cycles."""
    cycles = [s.cycle for s in ctx.hist[:3]]
    if len(cycles) < 2:
        return []
    start, end = min(c.start for c in cycles), max(c.end for c in cycles)
    p = txn_parts()
    rows = ctx.session.execute(
        select(Transaction.date, p.c.amount)
        .join(p, p.c.txn_id == Transaction.id)
        .join(Account, Account.id == Transaction.account_id)
        .join(Category, Category.id == p.c.category_id)
        .where(counted(), Category.name == EATING_OUT, Transaction.date.between(start, end))
    )
    spent = {True: Decimal(0), False: Decimal(0)}
    for d, amt in rows:
        spent[d.weekday() in WEEKEND] -= amt
    days = {True: 0, False: 0}
    d = start
    while d <= end:
        days[d.weekday() in WEEKEND] += 1
        d += timedelta(days=1)
    we, wd = spent[True] / days[True], spent[False] / days[False]
    if spent[True] + spent[False] < 300 or min(we, wd) <= 0:
        return []
    weekend_more = we >= wd * RATIO
    if not weekend_more and wd < we * RATIO:
        return []
    hi, lo = (we, wd) if weekend_more else (wd, we)
    when, other = ("בסופי השבוע", "באמצע השבוע") if weekend_more else ("באמצע השבוע", "בסופי השבוע")
    return [
        Insight(
            f"eating_out_weekend:{ctx.cycle.start}",
            "eating_out_weekend",
            "info",
            f"אוכל בחוץ: {when} יותר",
            f"בשלושת החודשים האחרונים יצאו על אוכל בחוץ {when} בממוצע {ils(hi)} ביום, "
            f"לעומת {ils(lo)} ביום {other}, פי {hi / lo:.1f}.",
            "לתזרים",
            ctx.cashflow_link,
            spent[weekend_more] - lo * days[weekend_more],
        )
    ]


def fixed_not_charged(ctx: Ctx) -> list[Insight]:
    """A confirmed fixed expense whose usual day passed without a charge this cycle."""
    late = ctx.today - timedelta(days=OVERDUE_DAYS)
    out = []
    for x in ctx.plan.still_expected:
        if x.source != "recurring" or x.recurring_id is None or x.date >= late:
            continue
        key = f"fixed_not_charged:{ctx.cycle.start}:{x.recurring_id}"
        out.append(
            Insight(
                key,
                "fixed_not_charged",
                "warning",
                "הוצאה קבועה שעוד לא ירדה",
                f"ההוצאה הקבועה {x.label} בסך {ils(x.amount)} לא ירדה עדיין "
                f"(בדרך כלל יורדת ב־{x.date:%d.%m}).",
                amount=x.amount,
                actions=[
                    {
                        "label": "לא יורדת החודש",
                        "method": "POST",
                        "path": f"/recurring/{x.recurring_id}/skip",
                    },
                    {
                        "label": "עדיין צפויה",
                        "method": "POST",
                        "path": f"/insights/{key}/snooze",
                    },
                ],
            )
        )
    return out


RULES = (
    negative_cycle,
    low_balance_before_income,
    idle_cash,
    no_goal,
    goal_status,
    category_trend,
    saving_capacity,
    fixed_heavy,
    fees,
    unknown_card,
    variable_income_expected,
    eating_out_weekend,
    fixed_not_charged,
)


def run(session: Session, today: date, rules=RULES) -> list[Insight]:
    """Run rules (one failing rule doesn't stop the rest), sorted; no dismiss filter, no cap."""
    ctx = Ctx(session, today, cycle_for(today, get_start_day(session)))
    out: list[Insight] = []
    for rule in rules:
        try:
            with session.begin_nested():
                out += rule(ctx)
        except Exception as e:  # noqa: BLE001 - one broken insight must not hide the rest
            log.error("insight %s failed: %s", rule.__name__, type(e).__name__)
    out.sort(key=lambda i: (ORDER[i.severity], -abs(i.amount or 0)))
    return out


def hidden(session: Session) -> set[str]:
    """Keys currently dismissed or snoozed."""
    now = datetime.now(UTC)
    return {
        s.key
        for s in session.scalars(select(InsightState))
        if s.dismissed or (s.dismissed_until and s.dismissed_until > now)
    }


def compute_insights(session: Session, today: date) -> list[Insight]:
    h = hidden(session)
    return [i for i in run(session, today) if i.key not in h][:CAP]


def _state(session: Session, key: str) -> InsightState:
    cutoff = datetime.now(UTC) - timedelta(days=PRUNE_DAYS)
    session.execute(delete(InsightState).where(InsightState.updated_at < cutoff))
    s = session.scalar(select(InsightState).where(InsightState.key == key))
    if s is None:
        s = InsightState(key=key)
        session.add(s)
    return s


def snooze(session: Session, key: str) -> None:
    _state(session, key).dismissed_until = datetime.now(UTC) + timedelta(days=SNOOZE_DAYS)
    session.flush()


def dismiss(session: Session, key: str) -> None:
    _state(session, key).dismissed = True
    session.flush()
