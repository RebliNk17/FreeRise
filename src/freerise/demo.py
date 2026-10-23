"""`freerise demo-seed`: realistic fake household data for demos. Never touches real data."""

import argparse
import os
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from freerise.auth import create_user
from freerise.cashflow.cycles import cycle_for, get_start_day
from freerise.categorize.normalize import normalize_merchant
from freerise.categorize.pipeline import categorize_pending
from freerise.config import get_settings
from freerise.crypto import encrypt_json
from freerise.forecast.next_cycle import add_months
from freerise.forecast.recurring import detect_recurring
from freerise.models import (
    Account,
    Balance,
    Category,
    Credential,
    Fund,
    FundDeposit,
    FundSnapshot,
    MerchantRule,
    SavingsPlan,
    Transaction,
    User,
)
from freerise.notify.rules import generate_notifications

CENT = Decimal("0.01")
MONTHS = 8

# description -> category name (seed rules, exact match on the normalized merchant)
SALARY = "משכורת אופק טכנולוגיות"
MORTGAGE = "משכנתא לאומי למשכנתאות"
ARNONA = "עיריית תל אביב ארנונה"
ELECTRIC = "חברת החשמל לישראל"
CELLCOM = "סלקום"
KINDERGARTEN = "גן הדובונים"
INSURANCE = "הראל ביטוח"
BILL_MAX = "מקס איט פיננסים"
BILL_ISRA = "ישראכרט"
BILL_CAL = "חיוב מ-כאל"
BILL_OTHER = "חיוב כרטיס פרימיום"
IKEA = "איקאה נתניה"
KSP = "KSP מחשבים"
SUPERMARKETS = ("שופרסל דיל", "רמי לוי", "יוחננוף", "ויקטורי")
RESTAURANTS = ("מסעדת הדסון", "קפה קפה", "בורגרים", "שיפודי התקווה")
WOLT = "WOLT"
FUEL = ("פז אפליקציה", "סונול", "דלק מוטורס")
SHOPS = ("זארה", "סופר-פארם", "אמזון")
# Fees: categorized by the 0009 seed contains-rules, not by RULES.
FEE_BANK = "עמלת פעולה בערוץ ישיר"
FEE_CARD = "דמי כרטיס"
FEE_FX = "עמלת המרת מט״ח"
RULES = {
    SALARY: "משכורת",
    MORTGAGE: "משכנתא",
    ARNONA: "ארנונה",
    ELECTRIC: "חשמל",
    CELLCOM: "תקשורת",
    KINDERGARTEN: "חינוך",
    INSURANCE: "ביטוח",
    BILL_MAX: "חיוב כרטיס אשראי",
    BILL_ISRA: "חיוב כרטיס אשראי",
    BILL_CAL: "חיוב כרטיס אשראי",
    BILL_OTHER: "חיוב כרטיס אשראי",
    IKEA: "קניות",
    KSP: "קניות",
    WOLT: "אוכל בחוץ",
    "זארה": "ביגוד והנעלה",
    "סופר-פארם": "פארמה",
    "אמזון": "קניות",
    **dict.fromkeys(SUPERMARKETS, "כלכלה"),
    **dict.fromkeys(RESTAURANTS, "אוכל בחוץ"),
    **dict.fromkeys(FUEL, "רכב"),
}
CONFIRM = (SALARY, MORTGAGE, ARNONA, ELECTRIC, CELLCOM, KINDERGARTEN, INSURANCE)


class DemoRefused(Exception):
    pass


def _money(x: float) -> Decimal:
    return Decimal(str(x)).quantize(CENT)


def seed_demo(session: Session, today: date, password: str) -> str:
    """Seed everything (flush only; caller commits). Returns the demo user's TOTP URI."""
    owners = set(session.scalars(select(Credential.owner)))
    users = set(session.scalars(select(User.username)))
    if owners - {"demo"} or users - {"demo"}:
        raise DemoRefused("real data exists; demo-seed only runs on an empty database")
    if owners or users:
        raise DemoRefused("demo data already seeded")

    rng = random.Random(42)
    _, uri = create_user(session, "demo", password)
    creds = {}
    # Card credentials carry real provider keys so bill reconciliation can match the issuer;
    # disabled so the scheduler never tries to scrape them.
    for provider, label in (("demo", "דמו"), ("max", "מקס דמו"), ("isracard", "ישראכרט דמו")):
        creds[provider] = Credential(
            provider=provider,
            label=label,
            owner="demo",
            secret_enc=encrypt_json({}),
            enabled=provider == "demo",
        )
        session.add(creds[provider])
    session.flush()
    cred = creds["demo"]
    accts = {}
    for key, kind, number, provider in (
        ("bank", "bank", "12-345-678901", "demo"),
        ("max", "card", "5326-1234", "max"),
        ("isra", "card", "4580-5678", "isracard"),
    ):
        accts[key] = Account(
            credential_id=creds[provider].id,
            provider_account_id=number,
            kind=kind,
            # The sync default, so the UI shows the provider label ("מקס ••1234").
            display_name=f"{creds[provider].label} {number[-4:]}",
        )
        session.add(accts[key])
    session.flush()

    cats = {c.name: c.id for c in session.scalars(select(Category))}
    for desc, cat in RULES.items():
        session.add(
            MerchantRule(
                pattern=normalize_merchant(desc),
                match="exact",
                category_id=cats[cat],
                source="seed",
            )
        )

    start = add_months(today, -MONTHS)
    rows: list[tuple[str, date, Decimal, str, int | None, int | None]] = []

    def add(acct: str, d: date, amount, desc: str, n: int | None = None, total: int | None = None):
        if start <= d <= today:
            rows.append((acct, d, _money(amount), desc, n, total))

    first = today.replace(day=1)
    for k in range(-MONTHS, 1):
        m = add_months(first, k)
        add("bank", m, 22000 + rng.randint(-150, 150), SALARY)
        add("bank", m.replace(day=10), -4000, MORTGAGE)
        if m.month % 2 == 0:
            add("bank", m.replace(day=15), -820, ARNONA)
        add("bank", m.replace(day=20), -rng.uniform(300, 520), ELECTRIC)
        # Moved from the Max card to Isracard about a month ago.
        cell = m.replace(day=5)
        add("isra" if cell > add_months(today, -1) else "max", cell, -160, CELLCOM)
        add("bank", m.replace(day=3), -3200, KINDERGARTEN)
        add("bank", m.replace(day=12), -450, INSURANCE)
        for _ in range(3):
            add(
                "max",
                m.replace(day=rng.randint(1, 28)),
                -rng.uniform(120, 380),
                rng.choice(RESTAURANTS),
            )
        for _ in range(4):
            add("isra", m.replace(day=rng.randint(1, 28)), -rng.uniform(70, 190), WOLT)
        for _ in range(2):
            add("max", m.replace(day=rng.randint(1, 28)), -rng.uniform(250, 380), rng.choice(FUEL))
        add("isra", m.replace(day=rng.randint(1, 28)), -rng.uniform(80, 450), rng.choice(SHOPS))
        add("bank", m.replace(day=25), -6.90, FEE_BANK)
        add("max", m.replace(day=8), -15, FEE_CARD)
    d = start
    while d <= today:
        add("max", d, -rng.uniform(250, 600), rng.choice(SUPERMARKETS))
        d += timedelta(days=7)

    # Installments: 12×350 ends this cycle, 6×200 ends next cycle.
    cycle = cycle_for(today, get_start_day(session))
    add("isra", max(cycle.start, today - timedelta(days=2)), -12.40, FEE_FX)  # a new fee
    add("max", max(cycle.start, today - timedelta(days=1)), -1450, RESTAURANTS[0])  # a spike
    d0 = min(cycle.start + timedelta(days=3), today)
    for n in range(1, 13):
        add("max", add_months(d0, n - 12), -350, IKEA, n, 12)
    for n in range(1, 7):
        add("isra", add_months(d0, n - 5), -200, KSP, n, 6)

    # Card bills on the bank on the 2nd, for the previous month's card charges.
    def billed(d: date) -> date:
        return add_months(d.replace(day=1), 1).replace(day=2)

    bills: dict[tuple[str, date], Decimal] = {}
    for acct, d, amount, *_ in rows:
        if acct != "bank":
            bills[acct, billed(d)] = bills.get((acct, billed(d)), Decimal(0)) + amount
    for (acct, d), total in bills.items():
        add("bank", d, total, BILL_MAX if acct == "max" else BILL_ISRA)
    # Reconciliation demo: a Cal card and an unidentifiable card nobody connected...
    last_bill = max(d for _, d in bills if d <= today)
    add("bank", last_bill, -1240, BILL_CAL)
    add("bank", last_bill, -610, BILL_OTHER)
    # ...and one Isracard purchase the card site shows in the next bill (a mismatch).
    moved = next(r for r in rows if r[0] == "isra" and billed(r[1]) == last_bill and r[4] is None)

    for i, row in enumerate(sorted(rows, key=lambda r: r[1])):
        acct, d, amount, desc, n, total = row
        # Card processed_date is the billing date (as the card scrapers report it).
        processed = d if acct == "bank" else billed(d)
        session.add(
            Transaction(
                account_id=accts[acct].id,
                txn_key=f"demo-{i}",
                date=d,
                processed_date=add_months(processed, 1) if row is moved else processed,
                amount=amount,
                original_amount=amount,
                original_currency="ILS",
                description=desc,
                installment_number=n,
                installment_total=total,
                status="completed",
                raw={},
                merchant_key=normalize_merchant(desc),
            )
        )
    bank_total = sum((r[2] for r in rows if r[0] == "bank"), Decimal(0))
    session.add(
        Balance(
            account_id=accts["bank"].id,
            as_of=datetime.now(ZoneInfo(get_settings().tz)),
            balance=Decimal(8500) + bank_total,
        )
    )
    session.flush()
    categorize_pending(session)
    for item in detect_recurring(session, today):
        if item.merchant_key in {normalize_merchant(x) for x in CONFIRM}:
            item.status = "confirmed"
    session.flush()

    _seed_funds(session, cred.id, today, rng)
    session.add_all(
        [
            SavingsPlan(
                name="חופשה באילת",
                target_amount=Decimal(6000),
                target_date=add_months(today, 8),
                saved_amount=Decimal(1500),
            ),
            SavingsPlan(
                name="החלפת רכב",
                target_amount=Decimal(40000),
                target_date=add_months(today, 24),
                saved_amount=Decimal(8000),
            ),
        ]
    )
    session.flush()
    generate_notifications(session, today)
    return uri


def _seed_funds(session: Session, credential_id: int, today: date, rng: random.Random) -> None:
    for policy, ptype, pension_type, name, company, balance, deposit in (
        ("DEMO-P-1", "קרן פנסיה", "makifa", "מגדל מקפת אישית", "מגדל", 310_000.0, 2900),
        ("DEMO-H-1", "קרן השתלמות", None, "הראל השתלמות כללי", "הראל", 145_000.0, 1500),
    ):
        fund = Fund(
            credential_id=credential_id,
            policy_id=policy,
            product_type=ptype,
            pension_type=pension_type,
            name=name,
            company=company,
            fee_deposit_pct=Decimal("1.5") if pension_type else None,
            fee_savings_pct=Decimal("0.22"),
            owner="demo",
        )
        session.add(fund)
        session.flush()
        for k in range(-18, 0):
            month_end = add_months(today.replace(day=1), k + 1) - timedelta(days=1)
            balance = balance * (1 + rng.gauss(0.006, 0.012)) + deposit
            session.add(
                FundDeposit(fund_id=fund.id, date=month_end.replace(day=10), amount=deposit)
            )
            session.add(FundSnapshot(fund_id=fund.id, as_of=month_end, balance=_money(balance)))
    session.flush()


def _cli(args: argparse.Namespace) -> None:
    if os.environ.get("FREERISE_ALLOW_DEMO") != "1":
        sys.exit("refusing: set FREERISE_ALLOW_DEMO=1 to seed demo data")
    from freerise.db import SessionLocal

    today = datetime.now(ZoneInfo(get_settings().tz)).date()
    try:
        with SessionLocal.begin() as s:
            uri = seed_demo(s, today, os.environ.get("FREERISE_DEMO_PASSWORD", "demo-demo-demo"))
    except DemoRefused as e:
        sys.exit(f"refusing: {e}")
    print(f"demo user 'demo' created. Add to your authenticator app:\n{uri}")


COMMANDS = {"demo-seed": (lambda p: None, _cli)}
