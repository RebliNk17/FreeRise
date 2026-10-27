from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from importlib.metadata import version

import pytest

from freerise.api import routes_auth
from freerise.crypto import decrypt_json, encrypt_json
from freerise.models import (
    Account,
    Balance,
    Credential,
    Invite,
    OtpRequest,
    SyncRun,
    Transaction,
)

ROUTES = [
    ("post", "/api/auth/logout"),
    ("get", "/api/auth/me"),
    ("post", "/api/auth/password"),
    ("get", "/api/auth/users"),
    ("delete", "/api/auth/users/1"),
    ("post", "/api/auth/invites"),
    ("post", "/api/auth/totp/check"),
    ("get", "/api/providers"),
    ("get", "/api/credentials"),
    ("post", "/api/credentials"),
    ("patch", "/api/credentials/1"),
    ("delete", "/api/credentials/1"),
    ("get", "/api/accounts"),
    ("patch", "/api/accounts/1"),
    ("get", "/api/transactions"),
    ("post", "/api/sync"),
    ("get", "/api/sync/runs"),
    ("get", "/api/sync/otp"),
    ("post", "/api/sync/otp/1"),
    ("get", "/api/categories"),
    ("post", "/api/categories"),
    ("patch", "/api/categories/1"),
    ("get", "/api/categories/uncategorized"),
    ("put", "/api/categories/merchant"),
    ("put", "/api/transactions/1/category"),
    ("get", "/api/rules"),
    ("delete", "/api/rules/1"),
    ("get", "/api/cashflow/current"),
    ("get", "/api/cashflow/2026/9"),
    ("get", "/api/plan/current"),
    ("put", "/api/plan/goal"),
    ("get", "/api/forecast/next"),
    ("get", "/api/recurring"),
    ("put", "/api/recurring/1"),
    ("post", "/api/recurring/detect"),
    ("get", "/api/pension/funds"),
    ("get", "/api/pension/funds/1"),
    ("get", "/api/notifications"),
    ("get", "/api/notifications/unread-count"),
    ("post", "/api/notifications/1/read"),
    ("post", "/api/notifications/read-all"),
    ("get", "/api/reconcile/current"),
    ("get", "/api/reconcile/2026/9"),
    ("get", "/api/settings"),
    ("put", "/api/settings"),
    ("get", "/api/insights"),
    ("post", "/api/insights/fees:2026-10-10/snooze"),
    ("post", "/api/insights/fees:2026-10-10/dismiss"),
    ("get", "/api/progress"),
    ("get", "/api/plans"),
    ("post", "/api/plans"),
    ("patch", "/api/plans/1"),
    ("delete", "/api/plans/1"),
    ("post", "/api/plans/1/contribute"),
    ("get", "/api/cost"),
    ("post", "/api/whatif"),
    ("get", "/api/home/current"),
    ("get", "/api/home/2026/9"),
    ("put", "/api/tracking/1"),
    ("put", "/api/tracking/1/expected"),
    ("put", "/api/tracking/1/weeks"),
    ("put", "/api/transactions/1/note"),
    ("post", "/api/transactions/move"),
]


@pytest.mark.parametrize("method,path", ROUTES)
def test_requires_auth(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_health_unauthenticated(client):
    assert client.get("/api/health").json() == {"ok": True, "version": version("freerise")}


def test_login_with_totp(client, user):
    bad = client.post(
        "/api/auth/login", json={"username": "shai", "password": user["password"], "totp": "000000"}
    )
    assert bad.status_code == 401
    r = client.post(
        "/api/auth/login",
        json={"username": "shai", "password": user["password"], "totp": user["totp"]()},
    )
    assert r.status_code == 204
    cookie = r.headers["set-cookie"]
    assert (
        "freerise_session=" in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    )
    assert "Secure" not in cookie
    assert client.get("/api/auth/me").json() == {"id": 1, "username": "shai", "name": "shai"}
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_login_rate_limited(client, user):
    for _ in range(5):
        r = client.post("/api/auth/login", json={"username": "shai", "password": "x", "totp": "1"})
        assert r.status_code == 401
    good = {"username": "shai", "password": user["password"], "totp": user["totp"]()}
    assert client.post("/api/auth/login", json=good).status_code == 429


def test_change_password(authed, user):
    from fastapi.testclient import TestClient

    from freerise.api.main import app

    other = TestClient(app)  # the same user on another device
    login = {"username": "shai", "password": user["password"], "totp": user["totp"]()}
    assert other.post("/api/auth/login", json=login).status_code == 204

    wrong = authed.post("/api/auth/password", json={"current": "nope", "new": "brand-new-pw"})
    assert wrong.status_code == 403  # not 401: that would bounce the app to the login page
    assert authed.get("/api/auth/me").status_code == 200
    short = authed.post("/api/auth/password", json={"current": user["password"], "new": "short"})
    assert short.status_code == 422

    ok = authed.post(
        "/api/auth/password", json={"current": user["password"], "new": "brand-new-pw"}
    )
    assert ok.status_code == 204
    assert authed.get("/api/auth/me").status_code == 200  # this device stays signed in
    assert other.get("/api/auth/me").status_code == 401  # the other one is signed out
    assert TestClient(app).post("/api/auth/login", json=login).status_code == 401
    new_login = {**login, "password": "brand-new-pw"}
    assert TestClient(app).post("/api/auth/login", json=new_login).status_code == 204


def test_change_password_rate_limited(authed, user):
    for _ in range(5):
        r = authed.post("/api/auth/password", json={"current": "x", "new": "brand-new-pw"})
        assert r.status_code == 403
    good = {"current": user["password"], "new": "brand-new-pw"}
    assert authed.post("/api/auth/password", json=good).status_code == 429


def test_household_invite(authed, user):
    from urllib.parse import parse_qs, urlparse

    import pyotp
    from fastapi.testclient import TestClient

    from freerise.api.main import app

    token = authed.post("/api/auth/invites").json()["token"]
    noa = TestClient(app)  # her phone: no session yet
    assert noa.get(f"/api/auth/invites/{token}").json() == {"invited_by": "shai"}
    join = {"token": token, "username": "noa", "password": "noa-pw-123"}
    assert noa.post("/api/auth/join", json={**join, "username": "shai"}).status_code == 409
    assert noa.post("/api/auth/join", json={**join, "password": "short"}).status_code == 422

    r = noa.post("/api/auth/join", json=join)
    assert r.status_code == 201 and r.json()["qr"].startswith("data:image/svg+xml")
    secret = parse_qs(urlparse(r.json()["otpauth"]).query)["secret"][0]
    # Joined and signed in; the link is spent.
    assert noa.post("/api/auth/totp/check", json={"code": "000000"}).status_code == 400
    code = pyotp.TOTP(secret).now()
    assert noa.post("/api/auth/totp/check", json={"code": code}).status_code == 204
    assert [m["username"] for m in noa.get("/api/auth/users").json()] == ["shai", "noa"]
    assert noa.get(f"/api/auth/invites/{token}").status_code == 404
    again = TestClient(app).post("/api/auth/join", json={**join, "username": "eve"})
    assert again.status_code == 404
    assert authed.get("/api/auth/invites/not-a-token").status_code == 404

    # Her own login works, with her authenticator.
    login = {"username": "noa", "password": "noa-pw-123", "totp": pyotp.TOTP(secret).now()}
    assert TestClient(app).post("/api/auth/login", json=login).status_code == 204


def test_display_names(authed):
    from fastapi.testclient import TestClient

    from freerise.api.main import app

    me = authed.get("/api/auth/me").json()
    assert me["name"] == "shai"  # the username until a name is picked
    assert authed.patch("/api/auth/me", json={"name": "   "}).status_code == 422
    r = authed.patch("/api/auth/me", json={"name": "  שי "})
    assert r.json() == {**me, "name": "שי"}  # the login username stays

    token = authed.post("/api/auth/invites").json()["token"]
    noa = TestClient(app)
    assert noa.get(f"/api/auth/invites/{token}").json() == {"invited_by": "שי"}
    join = {"token": token, "username": "noa", "password": "noa-pw-123", "name": "נועה"}
    assert noa.post("/api/auth/join", json=join).status_code == 201
    names = [(m["username"], m["name"]) for m in authed.get("/api/auth/users").json()]
    assert names == [("shai", "שי"), ("noa", "נועה")]


def test_remove_member(authed, user):
    from fastapi.testclient import TestClient

    from freerise.api.main import app

    token = authed.post("/api/auth/invites").json()["token"]
    noa = TestClient(app)
    join = {"token": token, "username": "noa", "password": "noa-pw-123"}
    assert noa.post("/api/auth/join", json=join).status_code == 201
    noa_id = noa.get("/api/auth/me").json()["id"]
    me = authed.get("/api/auth/me").json()

    selfie = noa.request("DELETE", f"/api/auth/users/{noa_id}", json={"current": "noa-pw-123"})
    assert selfie.status_code == 400  # nobody removes their own login
    url = f"/api/auth/users/{noa_id}"
    assert authed.request("DELETE", url, json={"current": "nope"}).status_code == 403
    assert authed.request("DELETE", url, json={"current": user["password"]}).status_code == 204
    assert noa.get("/api/auth/me").status_code == 401  # her sessions went with her
    assert [m["id"] for m in authed.get("/api/auth/users").json()] == [me["id"]]


def test_expired_invite(authed, sf):
    from sqlalchemy import update

    token = authed.post("/api/auth/invites").json()["token"]
    with sf() as s:
        s.execute(update(Invite).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
        s.commit()
    assert authed.get(f"/api/auth/invites/{token}").status_code == 404
    join = {"token": token, "username": "noa", "password": "noa-pw-123"}
    assert authed.post("/api/auth/join", json=join).status_code == 404


def test_providers(authed):
    items = authed.get("/api/providers").json()
    keys = [p["key"] for p in items]
    assert len(keys) == 22 and "hafenix" in keys and "migdal" in keys
    assert {
        "hapoalim",
        "pagi",
        "max",
        "visa cal",
        "behatsdaa",
        "hafenix",
        "migdal",
        "mislaka",
    } <= set(keys)
    services = [p["service"] for p in items]
    assert services == sorted(services, key=["banks", "credit_cards", "insurances"].index)
    by_key = {p["key"]: p for p in items}
    assert by_key["hapoalim"]["requires_2fa"] is True and by_key["leumi"]["requires_2fa"] is False


def test_credentials_never_return_plaintext(authed, sf):
    secret = "SuperSecret-Pa55"
    body = {
        "provider": "max",
        "label": "מקס",
        "owner": "שי",
        "fields": {"username": "shai_u", "password": secret},
    }
    assert (
        authed.post("/api/credentials", json={**body, "fields": {"username": "x"}}).status_code
        == 422
    )
    assert authed.post("/api/credentials", json={**body, "provider": "nope"}).status_code == 422
    r = authed.post("/api/credentials", json=body)
    assert r.status_code == 201
    cid = r.json()["id"]
    assert secret not in r.text and "shai_u" not in r.text
    assert authed.get("/api/credentials").json() == []  # unverified: hidden
    with sf() as s:
        s.get(Credential, cid).verified = True
        s.commit()
    listing = authed.get("/api/credentials")
    assert secret not in listing.text
    assert listing.json()[0]["fields"]["password"] == "••••"

    r = authed.patch(
        f"/api/credentials/{cid}",
        json={"label": "Max", "fields": {"password": "", "username": "shai_v"}},
    )
    assert r.status_code == 200 and secret not in r.text
    with sf() as s:
        c = s.get(Credential, cid)
        assert c.label == "Max"
        # new details wait for verification; the old ones stay in use
        assert decrypt_json(c.secret_enc) == {"username": "shai_u", "password": secret}
        assert decrypt_json(c.pending_secret_enc) == {"username": "shai_v", "password": secret}

    assert authed.delete(f"/api/credentials/{cid}").status_code == 204
    assert authed.get("/api/credentials").json() == []


def _seed_accounts(sf):
    with sf() as s:
        c = Credential(provider="max", label="Max", owner="שי", secret_enc=encrypt_json({}))
        s.add(c)
        s.flush()
        a1 = Account(credential_id=c.id, provider_account_id="1", kind="card", display_name="A")
        a2 = Account(
            credential_id=c.id,
            provider_account_id="2",
            kind="card",
            display_name="B",
            excluded=True,
        )
        s.add_all([a1, a2])
        s.flush()
        now = datetime.now(UTC)
        s.add_all(
            [
                Balance(account_id=a1.id, as_of=now - timedelta(days=1), balance=Decimal(1)),
                Balance(account_id=a1.id, as_of=now, balance=Decimal("250.50")),
            ]
        )
        for i, (acc, d) in enumerate([(a1, 1), (a1, 2), (a1, 2), (a2, 3)]):
            s.add(
                Transaction(
                    account_id=acc.id,
                    txn_key=f"k{i}",
                    date=date(2026, 10, d),
                    processed_date=date(2026, 10, d),
                    amount=Decimal("-10.25"),
                    description=f"shop {i}",
                    status="completed",
                    raw={},
                )
            )
        s.commit()
        return a1.id, a2.id


def test_accounts_balance_and_patch(authed, sf):
    a1, a2 = _seed_accounts(sf)
    accts = {a["id"]: a for a in authed.get("/api/accounts").json()}
    assert accts[a1]["balance"] == 250.5 and accts[a1]["provider"] == "max"
    assert accts[a1]["label"] == "A"
    assert accts[a2]["balance"] is None
    r = authed.patch(f"/api/accounts/{a1}", json={"display_name": "ראשי"})
    assert r.json()["display_name"] == "ראשי"
    assert authed.patch("/api/accounts/999", json={}).status_code == 404


def test_latest_balance_is_the_newest_reading(authed, sf):
    # A card reading dated on its charge day (ahead) mustn't hide a newer reading dated today.
    a1, _ = _seed_accounts(sf)
    now = datetime.now(UTC)
    with sf() as s:
        s.add(Balance(account_id=a1, as_of=now + timedelta(days=15), balance=Decimal("-12689.63")))
        s.flush()
        s.add(Balance(account_id=a1, as_of=now, balance=Decimal("-13483.86")))
        s.commit()
    accts = {a["id"]: a for a in authed.get("/api/accounts").json()}
    assert accts[a1]["balance"] == -13483.86


def test_excluded_account_hidden_by_default(authed, sf):
    _, a2 = _seed_accounts(sf)
    items = authed.get("/api/transactions").json()["items"]
    assert len(items) == 3 and all(i["account_id"] != a2 for i in items)
    assert items[0]["amount"] == -10.25 and items[0]["account_name"] == "A"
    items = authed.get("/api/transactions?include_excluded=true").json()["items"]
    assert len(items) == 4 and items[0]["account_id"] == a2


def test_transactions_cursor_and_filters(authed, sf):
    _seed_accounts(sf)
    seen = []
    url = "/api/transactions?limit=1&include_excluded=true"
    page = authed.get(url).json()
    while True:
        seen += [i["id"] for i in page["items"]]
        if not page["next_cursor"]:
            break
        page = authed.get(url + "&cursor=" + page["next_cursor"]).json()
    assert seen == [4, 3, 2, 1]
    assert authed.get("/api/transactions?cursor=garbage").status_code == 400
    r = authed.get("/api/transactions?q=SHOP 1&from=2026-10-02&to=2026-10-02").json()
    assert [i["id"] for i in r["items"]] == [2]


def test_one_sync_per_connection(authed, sf):
    """A second click joins the queued/running sync; a stale one (worker died) doesn't block."""
    with sf() as s:
        s.add(Credential(provider="max", label="Max", owner="a", secret_enc=encrypt_json({})))
        s.commit()
    ref = {"credential_id": 1, "run_id": 1}
    assert authed.post("/api/sync", json={"credential_id": 1}).json() == {
        "run_ids": [1],
        "runs": [{**ref, "already_running": False}],
    }
    assert authed.get("/api/credentials").json()[0]["syncing"] is True
    assert authed.post("/api/sync", json={"credential_id": 1}).json() == {
        "run_ids": [],
        "runs": [{**ref, "already_running": True}],
    }
    assert authed.post("/api/sync", json={}).json()["runs"] == [{**ref, "already_running": True}]
    with sf() as s:  # running for over 30 minutes: dead
        r = s.get(SyncRun, 1)
        r.status, r.started_at = "running", datetime.now(UTC) - timedelta(minutes=31)
        s.commit()
    assert authed.get("/api/credentials").json()[0]["syncing"] is False
    assert authed.post("/api/sync", json={"credential_id": 1}).json()["run_ids"] == [2]
    with sf() as s:
        s.get(SyncRun, 2).status = "success"
        s.commit()
    assert authed.get("/api/credentials").json()[0]["syncing"] is False


def test_manual_sync_creates_requested_run(authed, sf):
    with sf() as s:
        enc = encrypt_json({})
        s.add_all(
            [
                Credential(provider="max", label="Max", owner="a", secret_enc=enc),
                Credential(provider="amex", label="Off", owner="a", secret_enc=enc, enabled=False),
                Credential(provider="mislaka", label="Pension", owner="a", secret_enc=enc),
            ]
        )
        s.commit()
    r = authed.post("/api/sync", json={})
    assert r.json()["run_ids"] == [1]
    r = authed.post("/api/sync", json={"credential_id": 3})
    assert r.json()["run_ids"] == [2]
    assert authed.post("/api/sync", json={"credential_id": 99}).status_code == 404
    assert authed.post("/api/sync", json={"credential_id": 2}).status_code == 409
    runs = authed.get("/api/sync/runs").json()
    assert [(x["id"], x["status"], x["credential_label"]) for x in runs] == [
        (2, "requested", "Pension"),
        (1, "requested", "Max"),
    ]
    assert runs[0]["failure_kind"] is None
    with sf() as s:
        assert s.get(SyncRun, 1).trigger == "manual"
        s.add(
            SyncRun(
                credential_id=1,
                trigger="schedule",
                status="failed",
                failure_kind="provider_changed",
                finished_at=datetime(2026, 10, 22, tzinfo=UTC),
            )
        )
        s.commit()
    assert authed.get("/api/sync/runs").json()[0]["failure_kind"] == "provider_changed"
    creds = {c["id"]: c for c in authed.get("/api/credentials").json()}
    # unfinished "requested" runs don't hide the last finished run's kind
    assert creds[1]["last_failure_kind"] == "provider_changed"
    assert creds[3]["last_failure_kind"] is None


def test_answer_otp_flow(authed, sf):
    with sf() as s:
        c = Credential(provider="onezero", label="One", owner="a", secret_enc=encrypt_json({}))
        s.add(c)
        s.flush()
        run = SyncRun(credential_id=c.id, trigger="manual", status="running")
        s.add(run)
        s.flush()
        future = datetime.now(UTC) + timedelta(minutes=5)
        s.add_all(
            [
                OtpRequest(sync_run_id=run.id, status="waiting", expires_at=future),
                OtpRequest(
                    sync_run_id=run.id,
                    status="waiting",
                    expires_at=datetime.now(UTC) - timedelta(1),
                ),
            ]
        )
        s.commit()
    waiting = authed.get("/api/sync/otp").json()
    assert [(w["id"], w["credential_label"], w["provider"]) for w in waiting] == [
        (1, "One", "onezero")
    ]
    assert authed.post("/api/sync/otp/1", json={"code": "123456"}).status_code == 204
    assert authed.get("/api/sync/otp").json() == []
    assert authed.post("/api/sync/otp/1", json={"code": "123456"}).status_code == 400
    with sf() as s:
        assert s.get(OtpRequest, 1).status == "answered"


def test_secure_cookie_in_production(client, user, monkeypatch):
    from freerise.api import routes_auth
    from freerise.config import Settings

    prod = Settings(FREERISE_ENV="production")
    monkeypatch.setattr(routes_auth, "get_settings", lambda: prod)
    body = {"username": "shai", "password": user["password"], "totp": user["totp"]()}
    assert "Secure" in client.post("/api/auth/login", json=body).headers["set-cookie"]


def test_login_failure_recorded_before_verification(client, user, monkeypatch):
    seen = []

    def slow_verify(hash_, pw):
        seen.append(len(routes_auth._failures["shai"]))
        return False

    monkeypatch.setattr(routes_auth, "verify_password", slow_verify)
    for _ in range(5):
        assert (
            client.post(
                "/api/auth/login", json={"username": "shai", "password": "x", "totp": "1"}
            ).status_code
            == 401
        )
    assert seen == [1, 2, 3, 4, 5]  # each attempt counted while it is still being checked
    assert (
        client.post(
            "/api/auth/login", json={"username": "shai", "password": "x", "totp": "1"}
        ).status_code
        == 429
    )


def test_concurrent_bad_logins_capped():
    from concurrent.futures import ThreadPoolExecutor

    routes_auth._failures.clear()
    results = list(
        ThreadPoolExecutor(10).map(lambda _: routes_auth._claim_attempt("eve"), range(10))
    )
    assert results.count(True) == 5
    routes_auth._failures.clear()


def test_failure_window_prunes_idle_usernames(monkeypatch):
    routes_auth._failures.clear()
    routes_auth._claim_attempt("old")
    later = routes_auth.time.monotonic() + routes_auth.WINDOW_S + 1
    monkeypatch.setattr(routes_auth.time, "monotonic", lambda: later)
    routes_auth._claim_attempt("new")
    assert set(routes_auth._failures) == {"new"}
    routes_auth._failures.clear()


def test_docs_disabled_in_production():
    from freerise.api.main import doc_urls

    assert doc_urls("production") == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    assert doc_urls("development") == {}


def test_login_without_totp_when_disabled(client, user, monkeypatch):
    monkeypatch.setattr(routes_auth, "totp_required", lambda: False)
    assert client.get("/api/auth/config").json() == {"totp": False}
    r = client.post("/api/auth/login", json={"username": "shai", "password": "pw-123456"})
    assert r.status_code == 204
    bad = client.post("/api/auth/login", json={"username": "shai", "password": "wrong"})
    assert bad.status_code == 401


def test_login_requires_totp_by_default(client, user):
    assert client.get("/api/auth/config").json() == {"totp": True}
    r = client.post("/api/auth/login", json={"username": "shai", "password": "pw-123456"})
    assert r.status_code == 401


def test_totp_always_required_in_production(monkeypatch):
    from freerise.config import Settings

    s = Settings(FREERISE_ENV="production", FREERISE_LOGIN_TOTP=False)
    monkeypatch.setattr(routes_auth, "get_settings", lambda: s)
    assert routes_auth.totp_required() is True


def test_same_login_cannot_be_added_twice(authed, sf):
    card = {"id": "012345678", "card6Digits": "123456", "password": "pw-1"}
    body = {"provider": "amex", "label": "שי", "owner": "שי", "fields": card}
    first = authed.post("/api/credentials", json=body).json()["id"]
    # an abandoned, never-verified attempt for the same login is replaced, not duplicated
    second = authed.post("/api/credentials", json=body).json()["id"]
    with sf() as s:
        assert s.get(Credential, first) is None
        s.get(Credential, second).verified = True
        s.commit()
    # verified: refused, pointing at the existing one; whitespace/case don't matter
    again = {**body, "fields": {**card, "id": " 012345678 ", "password": "other"}}
    r = authed.post("/api/credentials", json=again)
    assert r.status_code == 409 and r.json()["detail"]["credential_id"] == second
    # another person's card on the same provider is fine
    other = {**body, "fields": {**card, "id": "999999999"}}
    third = authed.post("/api/credentials", json=other).json()["id"]
    with sf() as s:
        s.get(Credential, third).verified = True
        s.commit()
    # editing the other one into the same login is refused too
    r = authed.patch(f"/api/credentials/{third}", json={"fields": {"id": "012345678"}})
    assert r.status_code == 409


def test_details_show_ids_never_passwords(authed):
    fields = {"id": "012345678", "card6Digits": "123456", "password": "pw-secret"}
    cid = authed.post(
        "/api/credentials",
        json={"provider": "amex", "label": "שי", "owner": "שי", "fields": fields},
    ).json()["id"]
    r = authed.get(f"/api/credentials/{cid}/details")
    assert r.json() == {"id": "012345678", "card6Digits": "123456"}
    assert "pw-secret" not in r.text


def _post(client, provider, fields):
    body = {"provider": provider, "label": "x", "owner": "דנה", "fields": fields}
    return client.post("/api/credentials", json=body)


def test_any_complete_login_method_connects(authed, monkeypatch):
    by_key = {p["key"]: p for p in authed.get("/api/providers").json()}
    for key in ("max", "leumi", "onezero", "pepper", "hafenix", "migdal"):  # one way in
        assert by_key[key]["login_methods"] == [by_key[key]["required_fields"]]
    for key in ("visa cal", "isracard", "amex"):
        for i, method in enumerate(by_key[key]["login_methods"]):
            assert _post(authed, key, {f: f"{i}{f}" for f in method}).status_code == 201, (key, i)
    r = _post(authed, "visa cal", {"id": "012345678"})
    assert r.status_code == 422 and r.json()["detail"]["missing"] == ["card4Digits"]
    assert _post(authed, "visa cal", {"id": "1", "card8Digits": "12345678"}).status_code == 422
    # Max: username + password only, on either engine
    assert _post(authed, "max", {"id": "1", "card8Digits": "12345678"}).status_code == 422
    monkeypatch.setenv("FREERISE_IFS_PROVIDERS", "all,-max")
    assert _post(authed, "max", {"id": "1", "card8Digits": "12345678"}).status_code == 422


def test_max_shows_only_username_and_password(authed, sf):
    """The app API logs in with these two: a stored ID (the browser engine's) or device token
    isn't a form field."""
    cid = _post(authed, "max", {"username": "u", "password": "p"}).json()["id"]
    with sf() as s:
        c = s.get(Credential, cid)
        stored = {"username": "u", "password": "p", "id": "1", "otpLongTermToken": "t"}
        c.verified, c.secret_enc = True, encrypt_json(stored)
        s.commit()
    max_ = {p["key"]: p for p in authed.get("/api/providers").json()}["max"]
    assert max_["optional_fields"] == []
    assert authed.get("/api/credentials").json()[0]["fields"] == {
        "username": "••••",
        "password": "••••",
    }
    assert authed.patch(f"/api/credentials/{cid}", json={"fields": {"id": "2"}}).status_code == 422


def test_switching_login_method_drops_the_other_ones_fields(authed, sf):
    login = {"username": "u", "password": "pw-1"}
    cid = _post(authed, "visa cal", login).json()["id"]
    with sf() as s:
        c = s.get(Credential, cid)
        c.verified, c.secret_enc = True, encrypt_json({**login, "otpLongTermToken": "t"})
        s.commit()
    url = f"/api/credentials/{cid}"
    assert authed.patch(url, json={"method": 3}).status_code == 422
    r = authed.patch(url, json={"fields": {}, "method": 2})  # bank account left empty
    assert r.status_code == 422 and r.json()["detail"]["missing"] == ["id", "bankAccountNum"]
    # a stored password would win in the engine, so it goes; the device token stays
    r = authed.patch(url, json={"fields": {"id": "012345678", "card4Digits": "1234"}, "method": 1})
    assert r.status_code == 200 and r.json()["verify_run_id"]
    with sf() as s:
        c = s.get(Credential, cid)
        assert decrypt_json(c.pending_secret_enc) == {
            "id": "012345678",
            "card4Digits": "1234",
            "otpLongTermToken": "t",
        }
        assert decrypt_json(c.secret_enc)["password"] == "pw-1"  # in use until verified

    # Isracard: picking SMS with nothing else changed still re-verifies, without the password
    card = {"id": "999999999", "card6Digits": "123456", "password": "pw-2"}
    iid = _post(authed, "isracard", card).json()["id"]
    r = authed.patch(f"/api/credentials/{iid}", json={"fields": {}, "method": 1})
    assert r.json()["verify_run_id"]
    with sf() as s:
        assert decrypt_json(s.get(Credential, iid).secret_enc) == {
            "id": "999999999",
            "card6Digits": "123456",
        }


def test_same_login_refused_across_methods(authed, sf):
    cid = _post(authed, "visa cal", {"id": "012345678", "card4Digits": "1234"}).json()["id"]
    with sf() as s:
        s.get(Credential, cid).verified = True
        s.commit()
    r = _post(authed, "visa cal", {"id": "012345678", "bankAccountNum": "12-345-678"})
    assert r.status_code == 409 and r.json()["detail"]["credential_id"] == cid
    assert _post(authed, "visa cal", {"username": "u", "password": "p"}).status_code == 201
