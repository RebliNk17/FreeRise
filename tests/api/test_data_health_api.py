from datetime import date

from test_phase2_routes import _txn, ids  # noqa: F401 - fixture

from freerise.api import routes_accounts


def test_data_health(authed, ids, sf, monkeypatch):  # noqa: F811
    monkeypatch.setattr(routes_accounts, "today", lambda: date(2026, 10, 23))
    bill = ids["cats"]["חיוב כרטיס אשראי"]
    _txn(sf, ids["card"], date(2026, 7, 15), -50, "shop", cat=ids["cats"]["כלכלה"])
    _txn(sf, ids["card"], date(2026, 9, 15), -60, "shop")  # uncategorized
    _txn(sf, ids["bank"], date(2026, 10, 2), -500, "ישראכרט חיוב", cat=bill)
    h = authed.get("/api/data-health").json()
    assert h["ok"] is False
    (conn,) = h["connections"]
    assert conn["months_without_data"] == ["2026-08"]  # Oct is not over yet
    assert [a["id"] for a in h["idle_accounts"]] == []
    assert h["uncategorized"] == 1
    (b,) = h["card_bills"]
    assert (b["status"], b["amount"], b["issuer"]) == ("unknown_card", 500, "ישראכרט")
