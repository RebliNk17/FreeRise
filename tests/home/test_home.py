import itertools
from datetime import date
from decimal import Decimal

import pytest
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from freerise.accounts import account_label
from freerise.cashflow.cycles import cycle_by_label
from freerise.home.builder import DEFAULT_TRACKED, build_home
from freerise.models import (
    Account,
    Category,
    CategoryBudget,
    CategoryWeekBudget,
    Credential,
    RecurringItem,
    SavingsPlan,
    TrackedCategory,
    Transaction,
)

TODAY = date(2026, 10, 23)  # Friday; OCT = 10.10 (Sat) - 9.11
OCT = cycle_by_label(2026, 10, 10)
SEP = cycle_by_label(2026, 9, 10)
_seq = itertools.count()


def _acct(s, last4="1234", kind="card", excluded=False):
    cred = Credential(provider="max", label="מקס", owner="o", secret_enc=b"s")
    a = Account(
        credential=cred,
        provider_account_id=f"x{last4}",
        kind=kind,
        display_name=f"מקס {last4}",
        excluded=excluded,
    )
    s.add(a)
    s.flush()
    return a


def _cat(s, name):
    return s.scalar(select(Category.id).where(Category.name == name))


def _tx(s, a, d, amount, cat=None, key="m", **kw):
    t = Transaction(
        account_id=a.id,
        txn_key=f"h{next(_seq)}",
        date=d,
        processed_date=d,
        amount=Decimal(str(amount)),
        description=key,
        merchant_key=key,
        category_id=_cat(s, cat) if cat else None,
        status="completed",
        raw={},
        **kw,
    )
    s.add(t)
    s.flush()
    return t


def _rec(s, key, cat, amount, nxt, direction="expense", account=None):
    r = RecurringItem(
        merchant_key=key,
        direction=direction,
        label=cat,
        category_id=_cat(s, cat),
        cadence="monthly",
        amount_kind="fixed",
        expected_amount=Decimal(amount),
        last_date=date(2026, 9, 15),
        next_expected_date=nxt,
        status="confirmed",
        basis="b",
        account_id=account.id if account else None,
    )
    s.add(r)
    s.flush()
    return r


def _home(s, cycle=OCT, today=TODAY):
    return jsonable_encoder(build_home(s, cycle, today))


def _all_txn_ids(h):
    ids = {t["id"] for w in h["variable"]["weeks"] for t in w["transactions"]}
    ids |= {t["id"] for c in h["tracked"] for t in c["transactions"]}
    ids |= {t["id"] for t in h["savings"]["transactions"]}
    ids |= {t["id"] for t in h["income"]["variable"]["transactions"]}
    for g in h["fixed"]["groups"] + h["income"]["fixed_groups"] + [h["fees"] or {"items": []}]:
        ids |= {t["id"] for i in g["items"] for t in i["transactions"]}
    return ids


def test_structure_matches_contract(session):
    a = _acct(session)
    _tx(session, a, date(2026, 10, 12), -50, "קניות", note="חלב")
    h = _home(session)
    assert set(h) == {
        "cycle",
        "summary",
        "variable",
        "tracked",
        "untracked_available",
        "savings",
        "fixed",
        "total",
        "income",
        "multi_holder",
        "moved_next",
        "fees",
    }
    assert h["cycle"] == {
        "start": "2026-10-10",
        "end": "2026-11-09",
        "label_year": 2026,
        "label_month": 10,
        "is_current": True,
        "prev": {"year": 2026, "month": 9},
        "next": None,
    }
    assert set(h["summary"]) == {
        "week_left",
        "next_week_allowance",
        "goal",
        "goal_personal",
        "goal_plans",
        "variable_allowance",
    }
    w = h["variable"]["weeks"][0]
    assert set(w) == {
        "index",
        "start",
        "end",
        "spent",
        "left",
        "expected",
        "is_current",
        "is_past",
        "transactions",
    }
    t = h["variable"]["weeks"][1]["transactions"][0]
    assert set(t) == {
        "id",
        "date",
        "amount",
        "description",
        "merchant_key",
        "category_id",
        "category_name",
        "group",
        "account_id",
        "account_label",
        "note",
        "installment_number",
        "installment_total",
        "status",
        "account_holder",
        "cycle_shift",
        "cycle_label",
        "fixed_income_id",
        "cycle_date_source",
        "split_total",
        "split",
        "review",
    }
    assert (t["amount"], t["note"], t["group"], t["account_label"]) == (
        -50,
        "חלב",
        "variable",
        account_label(a),
    )
    assert isinstance(h["variable"]["spent"], int | float)
    assert set(h["fixed"]) == {"spent", "expected", "groups"}
    assert set(h["income"]) == {"received", "expected", "fixed_groups", "variable"}
    assert set(h["savings"]) == {"spent", "expected", "transactions"}


def test_moved_to_next_cycle_stays_listed_on_current(session):
    a = _acct(session)
    moved = _tx(session, a, date(2026, 10, 20), -80, "קניות", cycle_date=date(2026, 11, 15))
    _tx(session, a, date(2026, 10, 21), -30, "קניות")
    h = _home(session)
    assert [t["id"] for t in h["moved_next"]["transactions"]] == [moved.id]
    assert h["moved_next"]["transactions"][0]["cycle_shift"] == "next"
    assert moved.id not in _all_txn_ids(h)
    assert h["variable"]["spent"] == 30
    # once that cycle is reachable (here: viewing a past cycle), nothing is listed
    later = _home(session, today=date(2026, 11, 20))
    assert later["moved_next"]["transactions"] == []


def test_exclusions(session):
    a = _acct(session)
    ex = _acct(session, "0001", excluded=True)
    keep = _tx(session, a, date(2026, 10, 12), -50, "קניות")
    gone = [
        _tx(session, ex, date(2026, 10, 12), -70, "קניות"),
        _tx(session, a, date(2026, 10, 12), -80, "העברות"),
        _tx(session, a, date(2026, 10, 12), -90, "חיוב כרטיס אשראי"),
        _tx(session, a, date(2026, 10, 12), -95, "להתעלם"),
    ]
    unc = _tx(session, a, date(2026, 10, 13), -10)  # uncategorized negative -> variable
    h = _home(session)
    assert _all_txn_ids(h) == {keep.id, unc.id}
    assert h["variable"]["spent"] == 60
    assert not {g.id for g in gone} & _all_txn_ids(h)


def test_weekly_split_and_overrides(session):
    a = _acct(session)
    cid = _cat(session, "כלכלה")
    session.add(TrackedCategory(category_id=cid, mode="weekly"))
    session.add(CategoryBudget(cycle_start=OCT.start, category_id=cid, amount=Decimal(1000)))
    session.add(
        CategoryWeekBudget(cycle_start=OCT.start, category_id=cid, week_index=3, amount=200)
    )
    _tx(session, a, date(2026, 10, 12), -100, "כלכלה")  # week 1 (past)
    _tx(session, a, date(2026, 10, 20), -40, "כלכלה")  # week 2 (current)
    (t,) = _home(session)["tracked"]
    assert (t["expected"], t["expected_overridden"], t["spent"], t["left"]) == (
        1000,
        True,
        140,
        860,
    )
    weeks = t["weeks"]
    assert [w["start"] for w in weeks] == [
        "2026-10-10",
        "2026-10-11",
        "2026-10-18",
        "2026-10-25",
        "2026-11-01",
        "2026-11-08",
    ]
    # days 1/7/7/7/7/2: past weeks keep their planned share of 1000/31 days (left 0); the
    # 700 left after past spending (100) and the week override (200) go 43.75/day over 16 days
    assert [w["expected"] for w in weeks] == [32.26, 225.81, 306.25, 200, 306.25, 87.5]
    assert weeks[2]["is_current"] and weeks[1]["is_past"]
    assert weeks[1]["left"] == 0
    assert weeks[2]["left"] == pytest.approx(266.25)
    assert [x["id"] for x in weeks[2]["transactions"]] == [t["transactions"][0]["id"]]


def test_tracked_defaults_and_median(session):
    a = _acct(session)
    for d, amt in ((date(2026, 9, 12), -400), (date(2026, 8, 12), -600)):
        _tx(session, a, d, amt, "כלכלה")
    _tx(session, a, date(2026, 9, 13), -70, "אוכל בחוץ")  # only one cycle -> not tracked
    h = _home(session)
    tracked = {t["name"]: t for t in h["tracked"]}
    assert set(DEFAULT_TRACKED) <= tracked.keys()  # the starter set, history or not
    t = tracked["כלכלה"]
    assert (t["name"], t["mode"], t["expected"], t["expected_overridden"]) == (
        "כלכלה",
        "weekly",
        500,  # median of the 2 cycles with data
        False,
    )
    assert [p["spent"] for p in t["history"]] == [0, 0, 0, 0, 600, 400]
    assert t["history"][-1] == {"label_year": 2026, "label_month": 9, "spent": 400}
    names = {c["name"] for c in h["untracked_available"]}
    assert not names & set(DEFAULT_TRACKED)
    food = session.scalar(select(Category.id).where(Category.name == "כלכלה"))
    mode = select(TrackedCategory.mode).where(TrackedCategory.category_id == food)
    assert session.scalar(mode) == "weekly"


def test_tracked_default_skips_zero_median(session):
    a = _acct(session)
    for m in (5, 6, 7, 8, 9):  # 5 cycles with data
        _tx(session, a, date(2026, m, 12), -100, "כלכלה")
    for m in (8, 9):  # spent in 2 of 5 -> median 0 -> not seeded (not a default)
        _tx(session, a, date(2026, m, 13), -70, "קניות")
    h = _home(session)
    assert [t["name"] for t in h["tracked"]] == list(DEFAULT_TRACKED)
    assert "קניות" in {c["name"] for c in h["untracked_available"]}


def test_fixed_items_status_and_accounts(session):
    card = _acct(session)
    bank = _acct(session, "8901", kind="bank")
    elec = _tx(session, card, date(2026, 10, 14), -310, "חשמל", key="elec")
    _rec(session, "elec", "חשמל", 300, date(2026, 11, 14), account=card)
    _rec(session, "water", "מים", 120, date(2026, 10, 18), account=bank)  # 5 days late
    _rec(session, "arnona", "ארנונה", 500, date(2026, 11, 2))
    mort = _tx(session, bank, date(2026, 10, 11), -4000, "משכנתא", key="bank-loan")
    h = _home(session)
    groups = {g["name"]: g for g in h["fixed"]["groups"]}
    (e,) = groups["חשמל"]["items"]
    assert (e["status"], e["actual_amount"], e["expected_amount"]) == ("charged", 310, 300)
    assert e["account_label"] == account_label(card) and e["recurring_id"]
    assert [x["id"] for x in e["transactions"]] == [elec.id]
    (w,) = groups["מים"]["items"]
    assert (w["status"], w["actual_amount"], w["expected_date"]) == ("overdue", 0, "2026-10-18")
    assert w["account_label"] == account_label(bank)
    (ar,) = groups["ארנונה"]["items"]
    assert (ar["status"], ar["account_label"]) == ("expected", None)
    (m,) = groups["משכנתא"]["items"]
    assert (m["status"], m["recurring_id"], m["transactions"][0]["id"]) == (
        "charged",
        None,
        mort.id,
    )
    assert m["account_label"] == account_label(bank)
    assert groups["מים"]["expected"] == 120 and groups["חשמל"]["expected"] == 310
    assert (h["fixed"]["spent"], h["fixed"]["expected"]) == (4310, 4930)


def test_income_groups_savings_totals(session):
    a = _acct(session, kind="bank")
    sal = _tx(session, a, date(2026, 10, 11), 15000, "משכורת", key="salary")
    _rec(session, "salary", "משכורת", 15000, date(2026, 11, 11), direction="income")
    _rec(session, "pension", "קצבאות", 2000, date(2026, 11, 1), direction="income")
    gift = _tx(session, a, date(2026, 10, 12), 300, "הכנסות אחרות", key="gift")
    dep = _tx(session, a, date(2026, 10, 15), -1000, "השקעה וחיסכון", key="dep")
    _tx(session, a, date(2026, 10, 16), -200, "כלכלה")
    _tx(session, a, date(2026, 10, 11), -5000, "משכנתא", key="loan")
    session.add(
        SavingsPlan(name="p", target_amount=6000, target_date=date(2027, 3, 15), saved_amount=0)
    )
    session.flush()
    h = _home(session)
    inc = h["income"]
    groups = {g["name"]: g for g in inc["fixed_groups"]}
    assert groups["משכורת"]["items"][0]["transactions"][0]["id"] == sal.id
    assert groups["קצבאות"]["items"][0]["status"] == "expected"
    assert [t["id"] for t in inc["variable"]["transactions"]] == [gift.id]
    assert (inc["received"], inc["expected"], inc["variable"]["received"]) == (
        15300,
        17300,
        300,
    )
    sav = h["savings"]
    assert [t["id"] for t in sav["transactions"]] == [dep.id]
    assert (sav["spent"], sav["expected"]) == (1000, 1000)  # 6000 over 6 cycles
    alloc = h["summary"]["variable_allowance"]
    assert h["summary"]["goal_plans"] == 1000
    assert alloc == 17300 - 5000 - h["summary"]["goal"]
    # כלכלה is tracked (₪200 spent, nothing expected): it reserves 200 of the allowance
    assert h["variable"]["allowance"] == alloc - 200
    assert h["variable"]["spent"] == 0
    assert h["total"] == {"spent": 5000 + 200 + 1000, "expected": 5000 + alloc + 1000}


def test_past_cycle(session):
    a = _acct(session)
    _tx(session, a, date(2026, 9, 12), -400, "כלכלה")
    _tx(session, a, date(2026, 8, 12), -100, "כלכלה")
    _tx(session, a, date(2026, 9, 11), -3000, "משכנתא", key="loan")
    session.add(TrackedCategory(category_id=_cat(session, "כלכלה"), mode="monthly"))
    h = _home(session, SEP)
    assert h["summary"] is None
    assert h["cycle"]["is_current"] is False
    assert h["cycle"]["next"] == {"year": 2026, "month": 10}
    assert h["variable"]["allowance"] == h["variable"]["spent"] == 0  # all in tracked כלכלה
    assert all(w["is_past"] and w["left"] == 0 for w in h["variable"]["weeks"])
    (t,) = h["tracked"]
    assert t["expected"] == t["spent"] == 400 and t["left"] == 0
    assert h["fixed"]["expected"] == h["fixed"]["spent"] == 3000
    assert h["total"]["expected"] == h["total"]["spent"]


def test_fees_get_their_own_section(session):
    a = _acct(session)
    _tx(session, a, date(2026, 10, 12), -17.9, "עמלות", "דמי כרטיס")
    _tx(session, a, date(2026, 10, 12), -60, "תקשורת", "סלקום")
    h = jsonable_encoder(build_home(session, OCT, TODAY))
    assert h["fees"]["spent"] == 17.9
    assert [i["label"] for i in h["fees"]["items"]] == ["דמי כרטיס"]
    assert "עמלות" not in {g["name"] for g in h["fixed"]["groups"]}
    assert h["total"]["spent"] == h["fixed"]["spent"] + 17.9 + h["variable"]["spent"]


def test_no_fees_no_section(session):
    _tx(session, _acct(session), date(2026, 10, 12), -60, "תקשורת", "סלקום")
    assert build_home(session, OCT, TODAY).fees is None
