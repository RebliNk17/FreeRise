from scraper.utils.proxy import httpx_proxy, playwright_proxy


def test_unset(monkeypatch):
    monkeypatch.delenv("FREERISE_SCRAPER_PROXY", raising=False)
    assert playwright_proxy() is None and httpx_proxy() is None


def test_empty_is_unset(monkeypatch):
    monkeypatch.setenv("FREERISE_SCRAPER_PROXY", "")
    assert playwright_proxy() is None


def test_with_credentials(monkeypatch):
    monkeypatch.setenv("FREERISE_SCRAPER_PROXY", "http://us%40er:p%3Ass@proxy.example:8080")
    assert playwright_proxy() == {
        "server": "http://proxy.example:8080",
        "username": "us@er",
        "password": "p:ss",
    }
    assert httpx_proxy() == "http://us%40er:p%3Ass@proxy.example:8080"


def test_without_credentials(monkeypatch):
    monkeypatch.setenv("FREERISE_SCRAPER_PROXY", "http://proxy.example:3128")
    assert playwright_proxy() == {"server": "http://proxy.example:3128"}


def test_malformed_does_not_leak(monkeypatch):
    import pytest

    for bad in ("secret-token", "user:pw@host:80"):
        monkeypatch.setenv("FREERISE_SCRAPER_PROXY", bad)
        with pytest.raises(ValueError) as e:
            playwright_proxy()
        assert bad not in str(e.value)


def test_no_port_user_only_ipv6(monkeypatch):
    monkeypatch.setenv("FREERISE_SCRAPER_PROXY", "http://proxy.example")
    assert playwright_proxy() == {"server": "http://proxy.example"}
    monkeypatch.setenv("FREERISE_SCRAPER_PROXY", "http://bob@proxy.example:1")
    assert playwright_proxy() == {
        "server": "http://proxy.example:1",
        "username": "bob",
        "password": "",
    }
    monkeypatch.setenv("FREERISE_SCRAPER_PROXY", "http://u:p@[::1]:8080")
    assert playwright_proxy()["server"] == "http://[::1]:8080"
