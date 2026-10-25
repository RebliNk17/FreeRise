from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from freerise.api import routes_auth
from freerise.crypto import decrypt_json, encrypt_json
from freerise.models import Account, Balance, Credential, OtpRequest, SyncRun, Transaction

ROUTES = [
    ("post", "/api/auth/logout"),
    ("get", "/api/auth/me"),
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
    assert client.get("/api/health").json() == {"ok": True}


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
    assert client.get("/api/auth/me").json() == {"id": 1, "username": "shai"}
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_login_rate_limited(client, user):
    for _ in range(5):
        r = client.post("/api/auth/login", json={"username": "shai", "password": "x", "totp": "1"})
        assert r.status_code == 401
    good = {"username": "shai", "password": user["password"], "totp": user["totp"]()}
    assert client.post("/api/auth/login", json=good).status_code == 429


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
        f"/api/credentials/{cid}", json={"label": "Max", "fields": {"password": "", "id": "123"}}
    )
    assert r.status_code == 200 and secret not in r.text
    with sf() as s:
        c = s.get(Credential, cid)
        assert c.label == "Max"
        # new details wait for verification; the old ones stay in use
        assert decrypt_json(c.secret_enc) == {"username": "shai_u", "password": secret}
        assert decrypt_json(c.pending_secret_enc) == {
            "username": "shai_u",
            "password": secret,
            "id": "123",
        }

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
    body = {"provider": provider, "label": "x", "owner": "שי", "fields": fields}
    return client.post("/api/credentials", json=body)


def test_any_complete_login_method_connects(authed, monkeypatch):
    by_key = {p["key"]: p for p in authed.get("/api/providers").json()}
    assert by_key["max"]["login_methods"] == [
        ["username", "password"],
        ["id", "card8Digits"],
        ["id", "bankAccountNum"],
    ]
    for key in ("leumi", "onezero", "pepper", "hafenix", "migdal"):  # one way in: unchanged
        assert by_key[key]["login_methods"] == [by_key[key]["required_fields"]]
    for key in ("max", "visa cal", "isracard", "amex"):
        for i, method in enumerate(by_key[key]["login_methods"]):
            assert _post(authed, key, {f: f"{i}{f}" for f in method}).status_code == 201, (key, i)
    r = _post(authed, "max", {"id": "012345678"})
    assert r.status_code == 422 and r.json()["detail"]["missing"] == ["card8Digits"]
    assert _post(authed, "max", {"id": "1", "card4Digits": "1234"}).status_code == 422  # Cal's
    # Max on the npm engine: username + password only
    monkeypatch.setenv("FREERISE_IFS_PROVIDERS", "all,-max")
    assert _post(authed, "max", {"id": "1", "card8Digits": "12345678"}).status_code == 422


def test_switching_login_method_drops_the_other_ones_fields(authed, sf):
    login = {"username": "u", "password": "pw-1", "id": "012345678"}
    cid = _post(authed, "max", login).json()["id"]
    with sf() as s:
        c = s.get(Credential, cid)
        c.verified, c.secret_enc = True, encrypt_json({**login, "otpLongTermToken": "t"})
        s.commit()
    url = f"/api/credentials/{cid}"
    assert authed.patch(url, json={"method": 3}).status_code == 422
    r = authed.patch(url, json={"fields": {}, "method": 2})  # bank account left empty
    assert r.status_code == 422 and r.json()["detail"]["missing"] == ["bankAccountNum"]
    # a stored password would win in the engine, so it goes; the ID and device token stay
    r = authed.patch(url, json={"fields": {"card8Digits": "12345678"}, "method": 1})
    assert r.status_code == 200 and r.json()["verify_run_id"]
    with sf() as s:
        c = s.get(Credential, cid)
        assert decrypt_json(c.pending_secret_enc) == {
            "id": "012345678",
            "card8Digits": "12345678",
            "otpLongTermToken": "t",
        }
        assert decrypt_json(c.secret_enc)["password"] == "pw-1"  # in use until verified

    # Isracard: picking SMS with nothing else changed still re-verifies, without the password
    card = {"id": "123456782", "card6Digits": "123456", "password": "pw-2"}
    iid = _post(authed, "isracard", card).json()["id"]
    r = authed.patch(f"/api/credentials/{iid}", json={"fields": {}, "method": 1})
    assert r.json()["verify_run_id"]
    with sf() as s:
        assert decrypt_json(s.get(Credential, iid).secret_enc) == {
            "id": "123456782",
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
