"""Weekly / monthly reports, and the Telegram feed (a message per new charge or installment deal).

Rules like those in rules.py (run from generate_notifications); reports go in-app and to
Telegram, the feed only to Telegram and only once turned on there."""

from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from freerise.accounts import account_labels
from freerise.cashflow.cycles import HE_MONTHS, cycle_for, get_start_day, prev_cycle
from freerise.cashflow.parts import txn_parts
from freerise.cashflow.plan import (
    CENT,
    _sunday,
    cycle_plan,
    get_goal,
    history,
    projected_month_end,
)
from freerise.cashflow.summary import UNCATEGORIZED, cycle_summary
from freerise.insights.engine import DISPLAY, ils
from freerise.models import Account, Category, Setting, Transaction
from freerise.notify.senders import telegram_kinds
from freerise.notify.store import notify
from freerise.notify.telegram import FEED
from freerise.view import counted

REPORT_LATE_DAYS = 2  # a report the worker missed is sent up to this late, then skipped
FEED_MARK = "telegram_feed_mark"  # the last transaction id the feed has looked at
FEED_LINES = 10
SPENDING = ("fixed", "variable", "savings")


def _top(cats: list[tuple[str, Decimal]]) -> str | None:
    cats = [(DISPLAY.get(n, n), t) for n, t in cats if t > 0 and n != UNCATEGORIZED][:3]
    return "הכי הרבה הלך על: " + " · ".join(f"{n} {ils(t)}" for n, t in cats) if cats else None


def _variable_by_category(s: Session, start: date, end: date) -> list[tuple[str, Decimal]]:
    """Variable spending between start and end by category, largest first (as on home)."""
    p = txn_parts()
    name, total = func.coalesce(Category.name, UNCATEGORIZED), -func.sum(p.c.amount)
    rows = s.execute(
        select(name, total)
        .select_from(Transaction)
        .join(p, p.c.txn_id == Transaction.id)
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Category, Category.id == p.c.category_id)
        .where(
            counted(),
            Transaction.date.between(start, end),
            or_(Transaction.installment_total.is_(None), Transaction.installment_total <= 1),
            or_(Category.group == "variable", Category.id.is_(None) & (p.c.amount < 0)),
        )
        .group_by(name)
        .order_by(total.desc())
    )
    return [(n, t) for n, t in rows]


def weekly_report(s: Session, today: date) -> None:
    """Sunday morning: last week's variable spending against its share, where it went, and
    where the month is heading."""
    sunday = _sunday(today)
    if (today - sunday).days > REPORT_LATE_DAYS:
        return
    end = sunday - timedelta(days=1)
    start = end - timedelta(days=6)
    then = cycle_plan(s, end)
    week = next(w for w in then.weeks if w.start <= end <= w.end)
    cats = _variable_by_category(s, start, end)
    if not week.spent and not cats:
        return  # nothing synced that week
    if week.allowance <= 0:
        lines = [f"הוצאתם {ils(week.spent)} על הוצאות משתנות"]
    elif week.spent <= week.allowance:
        lines = [f"✅ הוצאתם {ils(week.spent)} מתוך {ils(week.allowance)} שתוכננו להוצאות משתנות"]
    else:
        over = ils(week.spent - week.allowance)
        lines = [f"⚠️ הוצאתם {ils(week.spent)}, {over} יותר מ-{ils(week.allowance)} שתוכננו"]
    if top := _top(cats):
        lines.append(top)
    now = cycle_plan(s, today)
    end_of_month = projected_month_end(now, today, history(s, now.cycle)).quantize(CENT)
    sign = "פלוס" if end_of_month >= 0 else "מינוס"
    lines.append(f"צפי לסוף החודש: {sign} {ils(abs(end_of_month))}")
    if now.goal > 0:
        lines[-1] += f" (היעד: {ils(now.goal)})"
    cur = next(w for w in now.weeks if w.start <= today <= w.end)
    lines.append(
        f"השבוע נשארו לכם {ils(cur.left)} להוצאות משתנות 💪"
        if cur.left > 0
        else "לא נשארה יתרה להוצאות משתנות השבוע"
    )
    notify(
        s,
        "weekly_report",
        f"סיכום שבועי · {start:%d.%m}–{end:%d.%m}",
        "\n".join(lines),
        "/home",
        f"weekly_report:{start}",
    )


def monthly_report(s: Session, today: date) -> None:
    """A new cycle began: how the last one ended, and what this one is expected to look like."""
    start_day = get_start_day(s)
    cur = cycle_for(today, start_day)
    if (today - cur.start).days > REPORT_LATE_DAYS:
        return
    prev = prev_cycle(cur, start_day)
    ps = cycle_summary(s, prev)
    if not (ps.income or ps.spending):
        return
    name = HE_MONTHS[prev.label_month.month - 1]
    lines = [
        f"🎉 סיימתם את {name} בפלוס {ils(ps.net)}"
        if ps.net >= 0
        else f"😬 סיימתם את {name} במינוס {ils(-ps.net)}",
        f"הכנסות {ils(ps.income)} · הוצאות {ils(ps.spending)}",
    ]
    goal = get_goal(s, prev)
    if goal > 0:
        lines.append(
            f"🎯 עמדתם ביעד של {ils(goal)}"
            if ps.net >= goal
            else f"🎯 חסרו {ils(goal - ps.net)} ליעד של {ils(goal)}"
        )
    variable = next(g for g in ps.groups if g.group == "variable").categories
    if top := _top([(c.name, c.total) for c in sorted(variable, key=lambda c: -c.total)]):
        lines.append(top)
    before = cycle_summary(s, prev_cycle(prev, start_day))
    if before.spending and before.spending != ps.spending:
        diff = ps.spending - before.spending
        lines.append(f"{ils(abs(diff))} {'יותר' if diff > 0 else 'פחות'} הוצאות מהחודש שלפני")
    plan = cycle_plan(s, today)
    lines += [
        "",
        f"📅 התזרים הצפוי ל{HE_MONTHS[cur.label_month.month - 1]}:",
        f"הכנסות צפויות {ils(plan.expected_income)}",
        f"הוצאות קבועות צפויות {ils(plan.expected_fixed)}",
        *([f"יעד לסוף החודש {ils(plan.goal)}"] if plan.goal > 0 else []),
        f"נשאר להוצאות משתנות {ils(plan.variable_allowance)}",
    ]
    m = prev.label_month
    notify(
        s,
        "monthly_report",
        f"סיכום חודש {name}",
        "\n".join(lines),
        f"/home/{m.year}/{m.month}",
        f"monthly_report:{prev.start}",
    )


def telegram_feed(s: Session, today: date) -> None:
    """New charges / installment deals since the last run, for whoever turned them on in
    Telegram. The mark follows the newest transaction even while off, so turning it on never
    sends a backlog."""
    kinds = telegram_kinds(s) & set(FEED)
    top = s.scalar(select(func.max(Transaction.id))) or 0
    row = s.scalar(select(Setting).where(Setting.key == FEED_MARK))
    if row is None:
        s.add(Setting(key=FEED_MARK, value=top))
        return
    mark, row.value = int(row.value), top
    if not kinds or top <= mark:
        return
    cutoff = today - timedelta(days=7)
    new = s.scalars(
        select(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.id > mark,
            Transaction.id <= top,
            Account.excluded.is_(False),
            Transaction.amount < 0,
            # installments keep the purchase date; their charge date is the processed date
            or_(Transaction.date >= cutoff, Transaction.processed_date >= cutoff),
            # not the history a new connection brings in on its first sync
            Transaction.created_at > Account.created_at + timedelta(hours=1),
            Category.group.is_(None) | Category.group.in_(SPENDING),
        )
        .order_by(Transaction.date, Transaction.id)
    ).all()
    if not new:
        return
    labels = account_labels(s)
    deals = [t for t in new if (t.installment_total or 0) > 1]
    if "installment_new" in kinds:
        for t in deals:
            if t.installment_number == 1:
                total = f"{ils(abs(t.original_amount))} " if t.original_amount else ""
                notify(
                    s,
                    "installment_new",
                    "עסקת תשלומים חדשה",
                    f"{t.description}: {total}ב-{t.installment_total} תשלומים של "
                    f"{ils(-t.amount)} · {labels.get(t.account_id, '')}",
                    f"/search?{urlencode({'q': t.description})}",
                    f"installment_new:{t.id}",
                )
    if "installment_ended" in kinds:
        for t in deals:
            if t.installment_number == t.installment_total:
                notify(
                    s,
                    "installment_ended",
                    "עסקת תשלומים הסתיימה",
                    f"{t.description}: חויב התשלום האחרון ({t.installment_number}/"
                    f"{t.installment_total}) של {ils(-t.amount)} · {labels.get(t.account_id, '')}"
                    f"\nמהחודש הבא {ils(-t.amount)} פחות בחיובים 🎉",
                    f"/search?{urlencode({'q': t.description})}",
                    f"installment_ended:{t.id}",
                )
    if "new_payment" in kinds:
        # A deal's later payments aren't new; its first is, unless it gets its own message.
        pays = [
            t
            for t in new
            if (t.installment_total or 0) <= 1
            or (t.installment_number == 1 and "installment_new" not in kinds)
        ]
        if not pays:
            return
        lines = [
            f"• {t.description} {ils(-t.amount)} · {labels.get(t.account_id, '')}" for t in pays
        ]
        if len(lines) > FEED_LINES:
            lines[FEED_LINES:] = [f"ועוד {len(lines) - FEED_LINES}"]
        one = len(pays) == 1
        notify(
            s,
            "new_payment",
            "חיוב חדש" if one else f"{len(pays)} חיובים חדשים",
            "\n".join(lines),
            f"/search?{urlencode({'q': pays[0].description})}" if one else "/search",
            f"new_payment:{max(t.id for t in pays)}",
        )
