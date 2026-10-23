from datetime import date

from test_phase2_routes import _txn, ids  # noqa: F401 - fixture

from freerise.api import routes_whatif


def test_typical_month_averages_past_cycles(authed, ids, sf, monkeypatch):  # noqa: F811
    monkeypatch.setattr(routes_whatif, "today", lambda: date(2026, 10, 23))
    c = ids["cats"]
    for d, food in ((date(2026, 8, 15), -1000), (date(2026, 9, 15), -2000)):
        _txn(sf, ids["bank"], d, 10000, "salary", cat=c["משכורת"])
        _txn(sf, ids["bank"], d, -3000, "mortgage", cat=c["משכנתא"])
        _txn(sf, ids["card"], d, food, "super", cat=c["כלכלה"])
    body = authed.get("/api/whatif/typical").json()
    assert body["months"] == 2
    assert body["income"] == [{"label": "משכורת", "amount": 10000}]
    assert body["fixed"] == [{"label": "משכנתא", "amount": 3000}]
    assert body["variable"] == [{"label": "כלכלה", "amount": 1500}]
    assert body["savings"] == [] and "goal" in body
