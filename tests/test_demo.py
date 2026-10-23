from datetime import date

import pytest

from freerise import cli
from freerise.cashflow.plan import cycle_plan
from freerise.crypto import encrypt_json
from freerise.demo import DemoRefused, seed_demo
from freerise.forecast.next_cycle import next_cycle_forecast
from freerise.models import Credential, Notification, RecurringItem
from freerise.reconcile.card_bills import reconcile_range

TODAY = date(2026, 10, 23)


def test_demo_seed_feeds_plan_and_forecast(session):
    uri = seed_demo(session, TODAY, "demo-demo-demo")
    assert uri.startswith("otpauth://")
    plan = cycle_plan(session, TODAY)
    assert plan.categories and plan.weeks and plan.expected_income > 0
    fc = next_cycle_forecast(session, TODAY)
    assert fc.fixed_items and fc.income_items
    assert fc.installments_stopping_total == 350
    confirmed = session.query(RecurringItem).filter_by(status="confirmed").count()
    assert confirmed == 7
    assert session.query(Notification).count() > 0
    bills = reconcile_range(session, date(2026, 1, 1), TODAY)
    statuses = [b.status for b in bills]
    assert statuses.count("mismatch") == 1 and statuses.count("unknown_card") == 2
    assert statuses.count("matched") == len(bills) - 3 > 5
    assert next(b for b in bills if b.status == "mismatch").suggestions
    with pytest.raises(DemoRefused):
        seed_demo(session, TODAY, "x")


def test_demo_seed_refuses_with_real_credential(session):
    session.add(Credential(provider="max", label="m", owner="o", secret_enc=encrypt_json({})))
    session.flush()
    with pytest.raises(DemoRefused):
        seed_demo(session, TODAY, "x")


def test_demo_cli_requires_env(monkeypatch):
    monkeypatch.delenv("FREERISE_ALLOW_DEMO", raising=False)
    with pytest.raises(SystemExit, match="FREERISE_ALLOW_DEMO"):
        cli.main(["demo-seed"])


def test_demo_seed_refuses_with_real_user(session):
    from freerise.auth import create_user

    create_user(session, "shai", "a-real-password")
    with pytest.raises(DemoRefused, match="real data"):
        seed_demo(session, TODAY, "x")


def test_demo_seed_has_fees(session):
    from freerise.cashflow.cycles import cycle_for, get_start_day
    from freerise.cashflow.fees import fees_in_cycle

    seed_demo(session, TODAY, "demo-demo-demo")
    f = fees_in_cycle(session, cycle_for(TODAY, get_start_day(session)))
    assert f.total > 0 and f.new_fee_merchants == ["עמלת המרת מטח"]
    assert session.query(Notification).filter_by(kind="fees_paid").count() == 1


def test_demo_seed_moved_card(session):
    from freerise.categorize.normalize import normalize_merchant
    from freerise.demo import CELLCOM

    seed_demo(session, TODAY, "demo-demo-demo")
    fc = next_cycle_forecast(session, TODAY)
    line = next(x for x in fc.fixed_items if x.label == CELLCOM)
    assert (line.account_label, line.previous_account_label) == (
        "ישראכרט \u2066••5678\u2069",
        "מקס \u2066••1234\u2069",
    )
    item = session.query(RecurringItem).filter_by(merchant_key=normalize_merchant(CELLCOM)).one()
    assert item.status == "confirmed"


def test_demo_seed_triggers_insights(session):
    from freerise.insights.engine import run
    from freerise.insights.progress import progress

    seed_demo(session, TODAY, "demo-demo-demo")
    kinds = {i.kind for i in run(session, TODAY)}
    assert {"idle_cash", "category_up", "fees", "unknown_card"} <= kinds
    p = progress(session, TODAY)
    assert len(p.cycles) == 6 and p.increases and p.decreases
