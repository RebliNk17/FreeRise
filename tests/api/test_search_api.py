from datetime import date

from sqlalchemy import update
from test_phase2_routes import _txn, ids  # noqa: F401 - fixture

from freerise.models import Account


def _q(authed, **params):
    return sorted(
        x["description"] for x in authed.get("/api/transactions", params=params).json()["items"]
    )


def test_search_one_box(authed, ids, sf):  # noqa: F811
    with sf() as s:
        s.execute(
            update(Account)
            .where(Account.id == ids["card"])
            .values(provider_account_id="4580123451234", holder="נועה")
        )
        s.commit()
    _txn(sf, ids["card"], date(2026, 9, 1), -119.95, "Falafel Hakosem", key="falafel hakosem")
    _txn(sf, ids["bank"], date(2026, 9, 2), -250, "Electric Co", cat=ids["cats"]["חשמל"])
    _txn(sf, ids["bank"], date(2026, 9, 3), 1200.5, "Refund")

    assert _q(authed, q="falafel") == ["Falafel Hakosem"]  # text
    assert _q(authed, q="1234") == ["Falafel Hakosem"]  # card's last 4 digits
    assert _q(authed, q="נועה") == ["Falafel Hakosem"]  # holder
    assert _q(authed, q="120") == ["Falafel Hakosem"]  # amount ±0.10
    assert _q(authed, q="1,200.50") == ["Refund"]  # credits too, commas ok
    assert _q(authed, q="200-300") == ["Electric Co"]  # range
    assert _q(authed, q="121") == []
    assert _q(authed, amount_min=200, amount_max=1300) == ["Electric Co", "Refund"]
    both = _q(authed, **{"from": "2026-09-02", "to": "2026-09-03"})
    assert both == ["Electric Co", "Refund"]
    item = authed.get("/api/transactions", params={"q": "Electric"}).json()["items"][0]
    assert item["group"] == "fixed" and item["review"] is None
