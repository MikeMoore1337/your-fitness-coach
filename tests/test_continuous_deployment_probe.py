from scripts import continuous_deployment_probe as probe
from scripts.check_deployment import HttpResponse


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def _response(path: str, *, status: int = 200, body: bytes = b"ok") -> HttpResponse:
    return HttpResponse(
        status=status,
        body=body,
        content_type="text/html",
        final_url=f"https://app.example.test{path}",
        headers={"cache-control": "public, immutable"},
    )


def test_probe_keeps_the_initial_asset_across_switch(monkeypatch) -> None:
    clock = FakeClock()
    reads: list[str] = []

    def read(_base_url: str, path: str, *, timeout: float) -> HttpResponse:
        assert timeout == 1
        reads.append(path)
        if path == "/app":
            return _response(
                path, body=b'<div id="root"></div><script src="/assets/a-old.js"></script>'
            )
        return _response(path, body=b"old asset")

    monkeypatch.setattr(probe, "_read", read)
    monkeypatch.setattr(probe, "check_deployment", lambda *args, **kwargs: "prod")

    report = probe.run_probe(
        "https://app.example.test",
        duration=2,
        interval=1,
        timeout=1,
        expected_environment="prod",
        clock=clock,
        sleeper=clock.sleep,
    )

    assert report.failure_count == 0
    assert report.compatibility_asset == "/assets/a-old.js"
    assert reads.count("/assets/a-old.js") == 3


def test_probe_classifies_broken_old_asset(monkeypatch) -> None:
    clock = FakeClock()

    def read(_base_url: str, path: str, *, timeout: float) -> HttpResponse:
        del timeout
        if path == "/app":
            return _response(
                path, body=b'<div id="root"></div><script src="/assets/a-old.js"></script>'
            )
        return _response(path, status=404, body=b"")

    monkeypatch.setattr(probe, "_read", read)
    monkeypatch.setattr(probe, "check_deployment", lambda *args, **kwargs: "prod")

    report = probe.run_probe(
        "https://app.example.test",
        duration=0,
        interval=1,
        timeout=1,
        expected_environment="prod",
        clock=clock,
        sleeper=clock.sleep,
    )

    assert report.failure_count == 1
    assert report.failures["asset_mismatch"] == 1


def test_probe_throttles_the_rate_limited_refresh_boundary(monkeypatch) -> None:
    clock = FakeClock()
    refresh_boundary_checks: list[bool] = []

    def read(_base_url: str, path: str, *, timeout: float) -> HttpResponse:
        del timeout
        if path == "/app":
            return _response(
                path, body=b'<div id="root"></div><script src="/assets/a-old.js"></script>'
            )
        return _response(path, body=b"old asset")

    def check(_base_url: str, **kwargs: object) -> str:
        refresh_boundary_checks.append(bool(kwargs["check_refresh_boundary"]))
        return "prod"

    monkeypatch.setattr(probe, "_read", read)
    monkeypatch.setattr(probe, "check_deployment", check)

    report = probe.run_probe(
        "https://app.example.test",
        duration=8,
        interval=1,
        timeout=1,
        expected_environment="prod",
        clock=clock,
        sleeper=clock.sleep,
    )

    assert report.failure_count == 0
    assert refresh_boundary_checks == [True, False, False, False, False, False, False, True, False]
    assert report.requests == 1 + sum(8 + int(value) for value in refresh_boundary_checks) + 9
