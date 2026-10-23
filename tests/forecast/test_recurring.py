from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from freerise.forecast.recurring import detect_recurring, set_status
from freerise.models import Account, Category, Credential, RecurringItem, Transaction

TODAY = date(2026, 10, 23)
_n = 0


def _acct(session, excluded=False):
    cred = Credential(provider="x", label="l", owner="o", secret_enc=b"s")
    acct = Account(
        credential=cred, provider_account_id="1", kind="bank", display_name="a", excluded=excluded
    )
    session.add(acct)
    session.flush()
    return acct


def _txns(session, acct, key, dated_amounts, **kw):
    global _n
    for d, amt in dated_amounts:
        _n += 1
        session.add(
            Transaction(
                account_id=acct.id,
                txn_key=f"k{_n}",
                date=d,
                processed_date=d,
                amount=Decimal(str(amt)),
                description=key,
                merchant_key=key,
                status="completed",
                raw={},
                **kw,
            )
        )
    session.flush()


def _monthly(start, amounts, day_step=30):
    return [(start + timedelta(days=day_step * i), a) for i, a in enumerate(amounts)]


def _by_key(items):
    return {i.merchant_key: i for i in items}


def test_monthly_fixed_detected(session):
    acct = _acct(session)
    _txns(session, acct, "שכירות", _monthly(date(2026, 5, 1), [-5000] * 6))
    item = _by_key(detect_recurring(session, TODAY))["שכירות"]
    assert item.direction == "expense"
    assert item.cadence == "monthly"
    assert item.amount_kind == "fixed"
    assert item.expected_amount == Decimal("5000.00")
    assert item.next_expected_date == item.last_date + timedelta(days=30)
    assert item.next_expected_date >= TODAY
    assert item.status == "confirmed"  # 3+ months, same amount and day: auto-confirmed
    assert item.basis


def test_variable_amount_bill_uses_median(session):
    acct = _acct(session)
    _txns(session, acct, "חשמל", _monthly(date(2026, 5, 1), [-300, -420, -350, -500, -380, -410]))
    item = _by_key(detect_recurring(session, TODAY))["חשמל"]
    assert item.amount_kind == "variable"
    assert item.expected_amount == Decimal("395.00")


def test_seasonal_uses_last_year_same_month(session):
    acct = _acct(session)
    # 13 monthly bills, last 2026-10-15 -> next 2026-11-14; last year's match 2025-11-19 (900)
    amounts = [-600, -900, -700, -500, -400, -300, -300, -320, -350, -330, -340, -360, -380]
    _txns(session, acct, "גז", _monthly(date(2025, 10, 20), amounts))
    item = _by_key(detect_recurring(session, TODAY))["גז"]
    assert item.amount_kind == "variable"
    assert item.next_expected_date == date(2026, 11, 14)
    assert item.expected_amount == Decimal("900.00")


def test_bimonthly_detected(session):
    acct = _acct(session)
    _txns(session, acct, "ארנונה", _monthly(date(2026, 1, 5), [-800] * 5, day_step=61))
    item = _by_key(detect_recurring(session, TODAY))["ארנונה"]
    assert item.cadence == "bimonthly"


def test_irregular_not_detected(session):
    acct = _acct(session)
    d = date(2026, 3, 1)
    dates = [d, d + timedelta(days=5), d + timedelta(days=50), d + timedelta(days=58)]
    dates += [d + timedelta(days=140), d + timedelta(days=200)]
    _txns(session, acct, "מסעדה", [(x, -100) for x in dates])
    assert "מסעדה" not in _by_key(detect_recurring(session, TODAY))


def test_installments_excluded(session):
    acct = _acct(session)
    _txns(
        session,
        acct,
        "מקרר",
        _monthly(date(2026, 5, 1), [-400] * 6),
        installment_number=1,
        installment_total=12,
    )
    assert "מקרר" not in _by_key(detect_recurring(session, TODAY))


def test_excluded_account_and_transfers_ignored(session):
    excl = _acct(session, excluded=True)
    _txns(session, excl, "שכירות", _monthly(date(2026, 5, 1), [-5000] * 6))
    acct = _acct(session)
    transfer = session.scalar(select(Category).where(Category.group == "transfer"))
    _txns(
        session,
        acct,
        "העברה",
        _monthly(date(2026, 5, 1), [-1000] * 6),
        category_id=transfer.id,
    )
    keys = _by_key(detect_recurring(session, TODAY))
    assert "שכירות" not in keys and "העברה" not in keys


def test_dismissed_stays_dismissed_on_redetect(session):
    acct = _acct(session)
    _txns(session, acct, "נטפליקס", _monthly(date(2026, 5, 1), [-50] * 6))
    item = _by_key(detect_recurring(session, TODAY))["נטפליקס"]
    set_status(session, item.id, "dismissed")
    _txns(session, acct, "נטפליקס", [(date(2026, 10, 28), -50)])
    assert "נטפליקס" not in _by_key(detect_recurring(session, date(2026, 10, 30)))
    rows = session.scalars(select(RecurringItem).where(RecurringItem.merchant_key == "נטפליקס"))
    (row,) = rows.all()
    assert row.status == "dismissed"


def test_income_uses_lower_quartile(session):
    acct = _acct(session)
    _txns(
        session,
        acct,
        "משכורת",
        _monthly(date(2026, 5, 1), [10000, 12000, 11000, 15000, 13000, 14000]),
    )
    item = _by_key(detect_recurring(session, TODAY))["משכורת"]
    assert item.direction == "income"
    # sorted 10000,11000,12000,13000,14000,15000 -> inclusive Q1 at idx 1.25 = 11250
    assert item.expected_amount == Decimal("11250.00")


def test_cancelled_subscription_not_detected(session):
    acct = _acct(session)
    _txns(session, acct, "ספוטיפיי", _monthly(date(2026, 1, 1), [-20] * 6))  # last 2026-05-31
    assert "ספוטיפיי" not in _by_key(detect_recurring(session, TODAY))


def test_stale_pending_row_removed(session):
    acct = _acct(session)
    amounts = [-20, -35, -20, -40, -20, -35]  # uneven: stays pending (not auto-confirmed)
    _txns(session, acct, "ספוטיפיי", _monthly(date(2026, 1, 1), amounts))
    assert "ספוטיפיי" in _by_key(detect_recurring(session, date(2026, 6, 10)))
    detect_recurring(session, TODAY)
    assert session.scalars(select(RecurringItem)).all() == []


def test_confirmed_survives_redetect(session):
    acct = _acct(session)
    _txns(session, acct, "ספוטיפיי", _monthly(date(2026, 1, 1), [-20] * 6))
    item = _by_key(detect_recurring(session, date(2026, 6, 10)))["ספוטיפיי"]
    set_status(session, item.id, "confirmed")
    detect_recurring(session, TODAY)
    (row,) = session.scalars(select(RecurringItem)).all()
    assert row.status == "confirmed"


def test_two_charges_same_month_not_monthly(session):
    acct = _acct(session)
    dates = [date(2026, m, d) for m in range(4, 10) for d in (1, 15)]
    _txns(session, acct, "חדר כושר", [(d, -150) for d in dates])
    assert "חדר כושר" not in _by_key(detect_recurring(session, TODAY))


def test_charge_and_refund_separate_directions(session):
    acct = _acct(session)
    _txns(session, acct, "ביטוח", _monthly(date(2026, 5, 1), [-300] * 6))
    _txns(session, acct, "ביטוח", _monthly(date(2026, 5, 3), [100] * 6))
    items = [i for i in detect_recurring(session, TODAY) if i.merchant_key == "ביטוח"]
    by_dir = {i.direction: i for i in items}
    assert by_dir["expense"].expected_amount == Decimal("300.00")
    assert by_dir["income"].expected_amount == Decimal("100.00")


def test_label_is_clean_merchant_name_category_in_basis(session):
    acct = _acct(session)
    cat = session.scalar(select(Category).where(Category.name == "חשמל"))
    _txns(session, acct, "חברת חשמל", _monthly(date(2026, 5, 1), [-300] * 6), category_id=cat.id)
    _txns(session, acct, "נטפליקס", _monthly(date(2026, 5, 1), [-50] * 6))
    items = _by_key(detect_recurring(session, TODAY))
    assert items["חברת חשמל"].label == "חברת חשמל"
    assert items["חברת חשמל"].basis.startswith("חברת חשמל · חשמל:")
    assert items["נטפליקס"].label == "נטפליקס"
    assert items["נטפליקס"].basis.startswith("נטפליקס:")


def test_fee_merchants_get_distinct_labels(session):
    acct = _acct(session)
    cat = session.scalar(select(Category).where(Category.name == "חשמל"))  # same category
    for key, desc in (("bank fee a", "Fee Alpha 12345"), ("bank fee b", "Fee Beta X9Y8Z7W6")):
        _txns(session, acct, desc, _monthly(date(2026, 5, 1), [-20] * 6), category_id=cat.id)
        session.query(Transaction).filter_by(description=desc).update({"merchant_key": key})
    items = _by_key(detect_recurring(session, TODAY))
    assert items["bank fee a"].label == "Fee Alpha"
    assert items["bank fee b"].label == "Fee Beta"
    assert items["bank fee a"].category_id == items["bank fee b"].category_id


def test_account_switch_tracked(session):
    old, new = _acct(session), _acct(session)
    start = TODAY - timedelta(days=150)
    _txns(session, old, "spotify", _monthly(start, [30, 30, 30, 30]))
    _txns(session, new, "spotify", [(start + timedelta(days=120), 30)])
    item = _by_key(detect_recurring(session, TODAY))["spotify"]
    assert (item.account_id, item.previous_account_id) == (new.id, old.id)
    assert item.account_changed_on == start + timedelta(days=120)
    item.status = "confirmed"
    detect_recurring(session, TODAY)  # re-run keeps status and the switch
    assert (item.status, item.account_id, item.previous_account_id) == ("confirmed", new.id, old.id)


def test_account_without_switch(session):
    a = _acct(session)
    _txns(session, a, "gym", _monthly(TODAY - timedelta(days=90), [200, 200, 200, 200]))
    item = _by_key(detect_recurring(session, TODAY))["gym"]
    assert (item.account_id, item.previous_account_id) == (a.id, None)


def test_account_flip_flop_is_not_a_switch(session):
    a, b = _acct(session), _acct(session)
    start = TODAY - timedelta(days=120)
    for i in range(5):  # A, B, A, B, A... paid from two cards
        _txns(session, (a, b)[i % 2], "groceries-co", [(start + timedelta(days=30 * i), 100)])
    item = _by_key(detect_recurring(session, TODAY))["groceries-co"]
    assert (item.account_id, item.previous_account_id) == (a.id, None)


def test_strong_monthly_is_auto_confirmed_uncertain_stays_pending(session):
    acct = _acct(session)
    _txns(session, acct, "gym", _monthly(date(2026, 7, 2), [-250, -250, -255, -250]))
    _txns(session, acct, "bill", _monthly(date(2026, 7, 2), [-300, -420, -350, -500]))  # amount
    days = [date(2026, 7, 2), date(2026, 8, 12), date(2026, 9, 5), date(2026, 10, 9)]
    _txns(session, acct, "drift", [(d, -100) for d in days])  # day wanders
    items = _by_key(detect_recurring(session, TODAY))
    assert items["gym"].status == "confirmed"
    assert items["bill"].status == "pending"
    assert "drift" not in items or items["drift"].status == "pending"


def test_auto_confirm_never_overrides_dismissed(session):
    acct = _acct(session)
    _txns(session, acct, "gym", _monthly(date(2026, 7, 2), [-250] * 4))
    item = _by_key(detect_recurring(session, TODAY))["gym"]
    set_status(session, item.id, "dismissed")
    detect_recurring(session, TODAY)
    assert item.status == "dismissed"


def test_sheet_category_change_follows_recurring(session):
    from freerise.categorize.pipeline import set_category

    acct = _acct(session)
    _txns(session, acct, "gym", _monthly(date(2026, 7, 2), [-250] * 4))
    item = _by_key(detect_recurring(session, TODAY))["gym"]
    t = session.scalar(select(Transaction).where(Transaction.merchant_key == "gym"))
    var = session.scalar(select(Category.id).where(Category.name == "ספורט"))
    fixed = session.scalar(select(Category.id).where(Category.name == "ביטוח"))
    set_category(session, t.id, var, remember=False)  # "זו לא הוצאה קבועה"
    assert item.status == "dismissed"
    set_category(session, t.id, fixed, remember=False)  # "זו הוצאה קבועה"
    assert item.status == "confirmed"
