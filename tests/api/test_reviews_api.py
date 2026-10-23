from datetime import date

from sqlalchemy import select, update
from test_phase2_routes import _txn, ids  # noqa: F401 - fixture

from freerise.models import Account, Notification


def test_review_flow(authed, ids, sf):  # noqa: F811
    t = _txn(sf, ids["card"], date(2026, 9, 1), -120, "Zara")
    assert authed.get("/api/reviews/people").json() == ["שי"]
    with sf() as s:
        s.execute(update(Account).where(Account.id == ids["card"]).values(holder="נועה"))
        s.commit()
    assert authed.get("/api/reviews/people").json() == ["נועה", "שי"]

    r = authed.put(f"/api/transactions/{t}/review", json={"assignee": "מישהו"})
    assert r.status_code == 422
    r = authed.put(f"/api/transactions/{t}/review", json={"assignee": "נועה", "note": " מה זה? "})
    assert r.status_code == 204
    (item,) = authed.get("/api/reviews").json()
    assert (item["transaction_id"], item["assignee"], item["note"], item["amount"]) == (
        t,
        "נועה",
        "מה זה?",
        -120,
    )
    with sf() as s:
        n = s.scalar(select(Notification).where(Notification.kind == "review"))
        assert n.title == "לבדוק עם נועה" and "Zara" in n.body and n.link == "/review"

    # no assignee: a shared "לבדיקה" flag; updating keeps one row
    assert authed.put(f"/api/transactions/{t}/review", json={}).status_code == 204
    (item,) = authed.get("/api/reviews").json()
    assert item["assignee"] is None

    assert authed.delete(f"/api/transactions/{t}/review").status_code == 204
    assert authed.get("/api/reviews").json() == []
