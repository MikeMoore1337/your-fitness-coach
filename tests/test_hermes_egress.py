from __future__ import annotations

import importlib.util
import ipaddress
import json
import os
import subprocess
from pathlib import Path

import pytest


def _load_module():
    path = Path(__file__).parents[1] / "deploy" / "hermes-discovery" / "hermes_egress.py"
    spec = importlib.util.spec_from_file_location("hermes_egress", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


egress = _load_module()


def test_source_hosts_include_only_enabled_canonical_fetch_hosts(tmp_path: Path) -> None:
    path = tmp_path / "source-definitions.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "hermes-source-definitions-v1",
                "sources": [
                    {
                        "enabled": True,
                        "url": "https://news.example.test/feed?topic=fitness",
                        "allowed_redirect_hosts": ["redirect.example.test"],
                        "allowed_item_hosts": ["items.example.test"],
                    },
                    {"enabled": False, "url": "https://disabled.example.test/feed"},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert egress._source_hosts(path) == {
        "news.example.test",
        "redirect.example.test",
        "items.example.test",
    }


def test_provider_and_intake_hosts_are_fixed_to_approved_contract() -> None:
    assert (
        egress._host_from_url("https://api.groq.com/openai/v1", expected=egress.PROVIDER_HOST)
        == "api.groq.com"
    )
    with pytest.raises(egress.EgressError, match="not_approved"):
        egress._host_from_url("https://api.openai.com/v1", expected=egress.PROVIDER_HOST)
    with pytest.raises(egress.EgressError, match="not_https"):
        egress._host_from_url(
            "https://api.groq.com/openai/v1?model=unexpected", expected=egress.PROVIDER_HOST
        )


def test_network_details_tolerates_builtin_network_without_ipam_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hermes_network = {
        "Id": "abcdef1234567890",
        "Driver": "bridge",
        "Options": {},
        "IPAM": {"Config": [{"Subnet": "172.31.0.0/24"}]},
        "Containers": {},
    }
    builtin_network = {"Driver": "host", "IPAM": {"Config": None}}

    def fake_run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["docker", "network", "inspect"]:
            document = hermes_network if args[3] == "hermes-net" else builtin_network
            return subprocess.CompletedProcess(args, 0, json.dumps([document]), "")
        if args[:3] == ["docker", "network", "ls"]:
            return subprocess.CompletedProcess(args, 0, "hermes-net\nhost\n", "")
        raise AssertionError(args)

    monkeypatch.setattr(egress, "_run", fake_run)

    bridge, subnets = egress._network_details("hermes-net")

    assert bridge == "br-abcdef123456"
    assert subnets == {ipaddress.ip_network("172.31.0.0/24")}


def test_build_rules_scopes_default_deny_to_hermes_subnet() -> None:
    rules = egress.build_rules(
        {ipaddress.ip_network("172.31.0.0/24")},
        {ipaddress.ip_address("203.0.113.10"), ipaddress.ip_address("2001:db8::10")},
        {ipaddress.ip_address("127.0.0.53")},
    )

    assert "type filter hook forward priority -100; policy accept" in rules
    assert "ip saddr { 172.31.0.0/24 } ct state established,related accept" in rules
    assert "ip saddr { 172.31.0.0/24 } ip daddr { 127.0.0.53 } udp dport 53 accept" in rules
    assert "ip daddr { 203.0.113.10 } tcp dport 443 accept" in rules
    assert "ip6 daddr { 2001:db8::10 } tcp dport 443 accept" not in rules
    assert "ip daddr { 0.0.0.0/8" in rules
    assert rules.rstrip().endswith("ip saddr { 172.31.0.0/24 } drop")
    assert "tcp dport 443 accept" in rules
    assert "ip saddr { 172.31.0.0/24 } ip daddr" in rules


def test_build_rules_allows_only_public_intake_hairpin_after_docker_dnat() -> None:
    rules = egress.build_rules(
        {ipaddress.ip_network("172.31.0.0/24")},
        {ipaddress.ip_address("203.0.113.10"), ipaddress.ip_address("77.91.90.171")},
        {ipaddress.ip_address("127.0.0.53")},
        {ipaddress.ip_address("77.91.90.171")},
    )

    assert (
        "ip saddr { 172.31.0.0/24 } ct original daddr { 77.91.90.171 } tcp dport 443 accept"
    ) in rules
    assert "ct original daddr { 172.28.0.10 }" not in rules


def test_build_rules_adds_scoped_host_input_default_deny() -> None:
    rules = egress.build_rules(
        {ipaddress.ip_network("172.31.0.0/24")},
        {ipaddress.ip_address("203.0.113.10")},
        {ipaddress.ip_address("127.0.0.53")},
        bridge="br-abcdef123456",
    )

    assert (
        "add chain inet hermes_egress input { type filter hook input priority -100; "
        "policy accept; }"
    ) in rules
    assert (
        'iifname "br-abcdef123456" ip saddr { 172.31.0.0/24 } '
        "ip daddr { 127.0.0.53 } udp dport 53 accept"
    ) in rules
    assert 'iifname "br-abcdef123456" ip saddr { 172.31.0.0/24 } drop' in rules


def test_build_rules_rejects_untrusted_bridge_name() -> None:
    with pytest.raises(egress.EgressError, match="docker_bridge_invalid"):
        egress.build_rules(
            {ipaddress.ip_network("172.31.0.0/24")},
            set(),
            set(),
            bridge="br;drop",
        )


def test_selected_worker_values_require_private_file_and_ignore_secrets(tmp_path: Path) -> None:
    path = tmp_path / "worker.env"
    path.write_text(
        "\n".join(
            [
                "HERMES_PROVIDER_BASE_URL=https://api.groq.com/openai/v1",
                "HERMES_PROVIDER_API_KEY=test-only-secret",
                "YFC_INTAKE_URL=https://app.your-fitness-coach.ru/api/v1/hermes/editorial/intake",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    if os.name == "posix":
        path.chmod(0o600)

    values = egress._selected_worker_values(path)

    assert values == {
        "HERMES_PROVIDER_BASE_URL": "https://api.groq.com/openai/v1",
        "YFC_INTAKE_URL": "https://app.your-fitness-coach.ru/api/v1/hermes/editorial/intake",
    }
