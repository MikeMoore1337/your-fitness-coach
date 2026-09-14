from __future__ import annotations

from collections.abc import Iterable


def _csp_directives(policy: str) -> dict[str, tuple[str, ...]]:
    directives: dict[str, tuple[str, ...]] = {}
    for raw_directive in policy.split(";"):
        tokens = tuple(raw_directive.split())
        if tokens:
            directives[tokens[0]] = tokens[1:]
    return directives


def _assert_sources(
    directives: dict[str, tuple[str, ...]], name: str, expected: Iterable[str]
) -> None:
    assert directives[name] == tuple(expected)


def test_production_csp_allows_yandex_metrica_and_public_api_without_relaxing_security(
    client, monkeypatch
) -> None:
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "landing_domain", "your-fitness-coach.ru")
    response = client.get("/", headers={"Host": "your-fitness-coach.ru"})
    assert response.status_code == 200

    policy = response.headers["content-security-policy"]
    directives = _csp_directives(policy)
    _assert_sources(
        directives,
        "script-src",
        ("'self'", "https://telegram.org", "https://mc.yandex.ru", "https://yastatic.net"),
    )
    _assert_sources(
        directives,
        "img-src",
        (
            "'self'",
            "data:",
            "blob:",
            "https://t.me",
            "https://*.telegram.org",
            "https://*.cdn-telegram.org",
            "https://mc.yandex.ru",
        ),
    )
    _assert_sources(
        directives,
        "connect-src",
        (
            "'self'",
            "https://app.your-fitness-coach.ru",
            "https://mc.yandex.ru",
            "https://mc.yandex.md",
            "wss://mc.yandex.ru",
        ),
    )
    _assert_sources(
        directives,
        "child-src",
        ("blob:", "https://mc.yandex.ru", "https://mc.yandex.md"),
    )
    _assert_sources(
        directives,
        "frame-src",
        ("blob:", "https://mc.yandex.ru", "https://mc.yandex.md"),
    )
    _assert_sources(directives, "worker-src", ("'self'",))
    _assert_sources(
        directives,
        "frame-ancestors",
        (
            "'self'",
            "https://web.telegram.org",
            "https://*.telegram.org",
            "https://metrika.yandex.ru",
            "https://metrica.yandex.ru",
        ),
    )

    assert directives["default-src"] == ("'self'",)
    assert directives["object-src"] == ("'none'",)
    assert directives["base-uri"] == ("'self'",)
    assert directives["form-action"] == ("'self'",)
    assert "'unsafe-inline'" not in directives["script-src"]
    assert "'unsafe-eval'" not in policy
    assert all(source != "https:" for sources in directives.values() for source in sources)
    assert "*" not in directives["script-src"]
    assert "*" not in directives["connect-src"]

    landing_api = client.get(
        "/api/v1/public/articles",
        headers={"Host": "your-fitness-coach.ru"},
        follow_redirects=False,
    )
    assert landing_api.status_code == 200
    assert "location" not in landing_api.headers
    assert "access-control-allow-origin" not in landing_api.headers
    assert landing_api.headers["content-security-policy"] == policy
    api_response = client.get(
        "/api/v1/public/articles",
        headers={"Host": "app.your-fitness-coach.ru"},
    )
    assert api_response.status_code == 200
    assert api_response.headers["content-security-policy"] == policy
