from datetime import date

from test_phase2_routes import _txn, ids  # noqa: F401 - fixture


def test_home_history(authed, ids, sf):  # noqa: F811
    for m in range(4, 10):
        _txn(sf, ids["card"], date(2026, m, 15), -100 * m, "shop", cat=ids["cats"]["כלכלה"])
    r = authed.get("/api/home/history", params={"kind": "variable", "year": 2026, "month": 10})
    body = r.json()
    assert [c["spent"] for c in body["cycles"]] == [400, 500, 600, 700, 800, 900]
    assert body["avg_spent"] == 650
    r = authed.get(
        "/api/home/history",
        params={"kind": "category", "category_id": ids["cats"]["כלכלה"], "year": 2026, "month": 10},
    )
    assert r.json()["cycles"][-1]["spent"] == 900
    assert authed.get("/api/home/history", params={"kind": "category"}).status_code == 422


def test_progress_history(authed, ids):  # noqa: F811
    r = authed.get("/api/progress/history", params={"group": "variable", "months": 3})
    assert r.status_code == 200
    assert len(r.json()["cycles"]) == 3
    assert authed.get("/api/progress/history", params={"group": "x"}).status_code == 422
