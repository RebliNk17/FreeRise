"""Alert rules. Each rule calls notify() with a dedup_key, so re-running is harmless."""

import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from statistics import median
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from freerise.cashflow.cycles import cycle_for, get_start_day, prev_cycle
from freerise.cashflow.fees import fees_in_cycle
from freerise.cashflow.plan import cycle_plan
from freerise.config import get_settings
from freerise.forecast.next_cycle import installments_ending
from freerise.insights import engine
from freerise.models import (
    Account,
    Category,
    Credential,
    RecurringItem,
    Setting,
    SyncRun,
    Transaction,
)
from freerise.models import (
    Notification as _N,
)
from freerise.notify.store import notify
from freerise.reconcile.card_bills import (
    HEALTH_LINK,
    ISSUER_NAMES,
    cards_synced_after,
    reconcile_range,
)
from freerise.sync.service import PAUSE_AFTER, login_paused

log = logging.getLogger("freerise.notify")
# Same labels as web/app/(app)/settings/credentials/page.tsx.
FAILURE_LABELS = {
    "auth_failed": "סיסמה שגויה",
    "provider_changed": "האתר השתנה",
    "timeout": "תם הזמן",
    "otp_timeout": "לא הוזן קוד",
    "other": "שגיאה",
}
NON_SPENDING = ("transfer", "card_bill", "ignore")
LARGE_MIN = Decimal(1500)  # default of the large_txn_min setting


def ils(x) -> str:
    return f"₪{Decimal(x):,.0f}"


def ils2(x) -> str:
    return f"₪{Decimal(x):,.2f}"


def charges_he(n: int) -> str:
    return "בחיוב אחד" if n == 1 else f"ב-{n} חיובים"


def _fees(s: Session, today: date) -> None:
    start_day = get_start_day(s)
    cycle = cycle_for(today, start_day)
    f = fees_in_cycle(s, cycle)
    link = f"/home/{cycle.label_month.year}/{cycle.label_month.month}"
    if f.total > 0:
        accounts = ", ".join(dict.fromkeys(x.account_name for x in f.items))
        notify(
            s,
            "fees_paid",
            "שולמו עמלות החודש",
            f"עד כה החודש שילמתם {ils2(f.total)} עמלות {charges_he(f.count)} ({accounts})",
            link,
            f"fees_paid:{cycle.start}",
        )
    # Burst guard: a freshly connected account has no history, so all its fees look new.
    prev_start = prev_cycle(cycle, start_day).start
    old_accounts = set(
        s.scalars(
            select(Transaction.account_id)
            .where(Transaction.date < prev_start)
            .group_by(Transaction.account_id)
        )
    )
    firsts = (
        next((i for i in f.items if i.fee_key == k and i.account_id in old_accounts), None)
        for k in f.new_fee_merchants
    )
    new = [x for x in firsts if x]
    if new:
        lines = [f"{x.description} {ils2(x.amount)} ({x.account_name})" for x in new[:3]]
        more = f" ועוד {len(new) - 3}" if len(new) > 3 else ""
        notify(
            s,
            "new_fee",
            "עמלה חדשה" if len(new) == 1 else "עמלות חדשות",
            ", ".join(lines) + more,
            link,
            f"new_fee:{cycle.start}",
            "warning",
        )


def _weekly_allowance_used(s: Session, today: date) -> None:
    plan = cycle_plan(s, today)
    for w in plan.weeks:
        if w.start <= today <= w.end and w.allowance > 0 and w.left <= 0:
            notify(
                s,
                "weekly_allowance_used",
                "תקציב השבוע נוצל",
                f"הוצאתם {ils(w.spent)} מתוך {ils(w.allowance)} לשבוע זה",
                "/forecast",
                f"weekly_allowance_used:{w.start}",
                "warning",
            )


def _category_over_expected(s: Session, today: date) -> None:
    plan = cycle_plan(s, today)
    for c in plan.categories:
        if c.expected > 0 and c.spent > c.expected * Decimal("1.2") and c.spent > 200:
            notify(
                s,
                "category_over_expected",
                f"חריגה בקטגוריה {c.name}",
                f"הוצאתם {ils(c.spent)} לעומת צפי של {ils(c.expected)}",
                "/forecast",
                f"category_over_expected:{plan.cycle.start}:{c.category_id}",
                "warning",
            )


def _installments_ending(s: Session, today: date) -> None:
    cycle = cycle_for(today, get_start_day(s))
    lines = installments_ending(s, cycle)
    total = sum((x.amount for x in lines), Decimal(0))
    if total > 0:
        notify(
            s,
            "installments_ending",
            "תשלומים מסתיימים",
            f"{'תשלום אחרון אחד' if len(lines) == 1 else f'{len(lines)} תשלומים אחרונים'} "
            f"במחזור הזה, {ils(total)} לא יחויבו במחזור הבא",
            "/forecast",
            f"installments_ending:{cycle.start}",
        )


def _large_transaction(s: Session, today: date) -> None:
    base = (
        select(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(Account.excluded.is_(False), Transaction.amount < 0)
        .where(Category.group.is_(None) | Category.group.not_in(NON_SPENDING))
    )
    recent = s.scalars(base.where(Transaction.date >= today - timedelta(days=3)))
    since = today - timedelta(days=183)
    v = s.scalar(select(Setting.value).where(Setting.key == "large_txn_min"))
    floor = Decimal(str(v)) if v is not None else LARGE_MIN
    for t in recent:
        limit = floor
        if t.category_id is not None:
            amts = [
                abs(a)
                for a in s.scalars(
                    select(Transaction.amount)
                    .join(Account, Account.id == Transaction.account_id)
                    .where(
                        Account.excluded.is_(False),
                        Transaction.category_id == t.category_id,
                        Transaction.amount < 0,
                        Transaction.date >= since,
                    )
                )
            ]
            limit = max(floor, 3 * median(amts))
        if abs(t.amount) > limit:
            notify(
                s,
                "large_transaction",
                "עסקה גדולה",
                f"{t.description}: {ils(abs(t.amount))}",
                f"/transactions?{urlencode({'q': t.description})}",
                f"large_transaction:{t.id}",
                "warning",
            )


def _uncategorized_growing(s: Session, today: date) -> None:
    n = s.scalar(
        select(func.count())
        .select_from(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .where(Account.excluded.is_(False), Transaction.category_id.is_(None))
    )
    if n > 20:
        y, w, _ = today.isocalendar()
        notify(
            s,
            "uncategorized_growing",
            "עסקאות ממתינות לסיווג",
            f"{n} עסקאות ללא קטגוריה",
            "/home?categorize=1",
            f"uncategorized_growing:{y}-W{w:02d}",
        )


def _pension_reminder(s: Session, today: date) -> None:
    if today.day < 21:
        return
    tz = ZoneInfo(get_settings().tz)
    start = datetime.combine(today.replace(day=1), time.min, tz)
    for c in s.scalars(
        select(Credential).where(
            Credential.provider == "mislaka", Credential.enabled, Credential.verified
        )
    ):
        ok = s.scalar(
            select(SyncRun.id)
            .where(
                SyncRun.credential_id == c.id,
                SyncRun.status == "success",
                SyncRun.finished_at >= start,
            )
            .limit(1)
        )
        if ok is None:
            notify(
                s,
                "pension_reminder",
                "זמן לעדכן נתוני פנסיה",
                f"טרם בוצע סנכרון מסלקה החודש ({c.label})",
                "/settings/credentials",
                f"pension_reminder:{c.id}:{today:%Y-%m}",
            )


def _sync_failed(s: Session, today: date) -> None:
    tz = ZoneInfo(get_settings().tz)
    since = datetime.combine(today - timedelta(days=2), time.min, tz)
    q = (
        # No enabled filter: an auth failure auto-disables the credential before this runs.
        select(SyncRun, Credential.label, Credential.enabled)
        .join(Credential, Credential.id == SyncRun.credential_id)
        .where(
            SyncRun.status.in_(("failed", "otp_timeout")),
            SyncRun.finished_at >= since,
            SyncRun.trigger != "verify",  # shown on the connecting screen instead
        )
    )
    for run, label, enabled in s.execute(q):
        kind = run.failure_kind or ("otp_timeout" if run.status == "otp_timeout" else "other")
        why = FAILURE_LABELS.get(kind, FAILURE_LABELS["other"])
        if (run.error or "").startswith("AUTOMATION_BLOCKED"):  # bucketed as provider_changed
            why = "הספק חוסם זמנית חיבור אוטומטי"
        if not enabled:
            why += " — הסנכרון הושבת — יש לעדכן סיסמה"
        notify(
            s,
            "sync_failed",
            f"סנכרון נכשל: {label}",
            why,
            "/settings/credentials",
            f"sync_failed:{run.id}",
            "critical",
        )


def _sync_paused(s: Session, today: date) -> None:
    """Scheduled syncs stopped after repeated login failures (sync/scheduler.py): say why."""
    for c in s.scalars(select(Credential).where(Credential.enabled, Credential.verified)):
        if not login_paused(s, c.id):
            continue
        last = s.scalar(
            select(func.max(SyncRun.id)).where(SyncRun.credential_id == c.id)
        )  # once per streak: the next run either clears it or starts a new key
        notify(
            s,
            "sync_paused",
            f"הסנכרון האוטומטי הושהה: {c.label}",
            f"ההתחברות נכשלה {PAUSE_AFTER} פעמים ברצף, ולכן הסנכרון האוטומטי הופסק כדי שהחשבון "
            "לא יינעל. היכנסו לאתר הספק וודאו שאפשר להתחבר (ושהחשבון לא נעול), ואז לחצו "
            "״סנכרון״ בעמוד החיבורים.",
            "/settings/credentials",
            f"sync_paused:{c.id}:{last}",
            "critical",
        )


def _new_recurring(s: Session, today: date) -> None:
    for r in s.scalars(select(RecurringItem).where(RecurringItem.status == "pending")):
        notify(
            s,
            "new_recurring",
            "זוהה חיוב קבוע חדש",
            f"{r.label}: {ils(r.expected_amount)}",
            "/forecast",  # where pending items are confirmed
            f"new_recurring:{r.id}",
        )


def _card_bills(s: Session, today: date) -> None:
    for b in reconcile_range(s, today - timedelta(days=45), today):
        name = ISSUER_NAMES.get(b.issuer, "לא ידוע")
        if b.status == "mismatch":
            # Deduped forever, so wait until the card side has caught up with this bill.
            if not cards_synced_after(s, b.issuer, b.date):
                continue
            detail = (
                f"חסרות בכרטיס עסקאות בסך {ils(b.gap)}"
                if b.gap > 0
                else f"בכרטיס {ils(-b.gap)} יותר מהחיוב"
            )
            notify(
                s,
                "card_bill_mismatch",
                f"חיוב {name} לא תואם",
                f"הבנק חויב {ils(b.amount)}, בכרטיס {ils(b.card_total)} — {detail}",
                HEALTH_LINK,
                f"card_bill_mismatch:{b.bank_txn_id}",
                "warning",
            )
        elif b.status == "unknown_card":
            who = f"כרטיס של {name}" if b.issuer else "כרטיס לא מזוהה"
            notify(
                s,
                "card_unknown",
                "חיוב מכרטיס לא מחובר",
                f"{who} חויב {ils(b.amount)} מהבנק אבל אין כרטיס מחובר שתואם",
                HEALTH_LINK,
                f"card_unknown:{b.bank_txn_id}",
                "warning",
            )


def _insight_warnings(s: Session, today: date) -> None:
    """Cash-flow warnings from the insights engine; keys carry the cycle start -> once a cycle.

    Dismissed / snoozed on home -> no notification either."""
    hidden = engine.hidden(s)
    for i in engine.run(s, today, (engine.negative_cycle, engine.low_balance_before_income)):
        if i.key in hidden:
            continue
        notify(s, i.kind, i.title, i.body, i.link, f"insight:{i.key}", "warning")


RULES = (
    _sync_failed,
    _sync_paused,
    _new_recurring,
    _weekly_allowance_used,
    _category_over_expected,
    _installments_ending,
    _large_transaction,
    _uncategorized_growing,
    _pension_reminder,
    _card_bills,
    _fees,
    _insight_warnings,
)


def generate_notifications(session: Session, today: date) -> int:
    """Run all rules; one failing rule doesn't stop the rest. Returns count created."""
    before = session.scalar(select(func.count()).select_from(_N))
    for rule in RULES:
        try:
            with session.begin_nested():
                rule(session, today)
        except Exception as e:  # noqa: BLE001
            log.error("notification rule %s failed: %s", rule.__name__, type(e).__name__)
    return session.scalar(select(func.count()).select_from(_N)) - before
