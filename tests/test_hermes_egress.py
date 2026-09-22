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
        mode=egress.COLOCATED_ISOLATED_MODE,
    )

    assert "type filter hook forward priority -100; policy accept" in rules
    assert "ip saddr { 172.31.0.0/24 } ct state established,related accept" in rules
    assert "ip saddr { 172.31.0.0/24 } ip daddr { 127.0.0.53 } udp dport 53 accept" in rules
    assert "ip daddr { 203.0.113.10 } tcp dport 443 accept" in rules
    assert "ip6 daddr { 2001:db8::10 } tcp dport 443 accept" not in rules
    assert "ip daddr { 0.0.0.0/8" in rules
    assert rules.rstrip().endswith("ip saddr { 172.31.0.0/24 } counter drop")
    assert "tcp dport 443 accept" in rules
    assert "ip saddr { 172.31.0.0/24 } ip daddr" in rules


def test_build_rules_allows_only_public_intake_hairpin_after_docker_dnat() -> None:
    rules = egress.build_rules(
        {ipaddress.ip_network("172.31.0.0/24")},
        {ipaddress.ip_address("203.0.113.10"), ipaddress.ip_address("77.91.90.171")},
        {ipaddress.ip_address("127.0.0.53")},
        {ipaddress.ip_address("77.91.90.171")},
        mode=egress.COLOCATED_ISOLATED_MODE,
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
        mode=egress.COLOCATED_ISOLATED_MODE,
    )

    assert (
        "add chain inet hermes_egress input { type filter hook input priority -100; "
        "policy accept; }"
    ) in rules
    assert (
        'iifname "br-abcdef123456" ip saddr { 172.31.0.0/24 } '
        "ip daddr { 127.0.0.53 } udp dport 53 accept"
    ) in rules
    assert 'iifname "br-abcdef123456" ip saddr { 172.31.0.0/24 } counter drop' in rules
    assert "tcp dport { 22, 25566 } counter drop" in rules


def test_build_rules_rejects_untrusted_bridge_name() -> None:
    with pytest.raises(egress.EgressError, match="docker_bridge_invalid"):
        egress.build_rules(
            {ipaddress.ip_network("172.31.0.0/24")},
            set(),
            set(),
            bridge="br;drop",
            mode=egress.COLOCATED_ISOLATED_MODE,
        )


def _separate_vm_rules(*, include_ipv6: bool = False) -> str:
    subnets = {ipaddress.ip_network("172.31.0.0/24")}
    if include_ipv6:
        subnets.add(ipaddress.ip_network("fd00:415::/64"))
    return egress.build_rules(
        subnets,
        set(),
        {ipaddress.ip_address("127.0.0.53")},
        bridge="br-abcdef123456",
        mode=egress.SEPARATE_VM_MODE,
    )


def test_separate_vm_public_https_does_not_use_host_dns_snapshot() -> None:
    rules = _separate_vm_rules()

    assert "ip daddr != {" in rules
    assert "tcp dport 443 accept" in rules
    assert "ip daddr { 150.171.109.196 } tcp dport 443 accept" not in rules
    assert "ip daddr { 150.171.109.198 } tcp dport 443 accept" not in rules


def test_separate_vm_dns_rotation_from_public_a_to_b_is_allowed() -> None:
    host_snapshot = ipaddress.ip_address("150.171.109.196")
    container_answer = ipaddress.ip_address("150.171.109.198")
    assert host_snapshot != container_answer

    rules = _separate_vm_rules()

    public_https = next(line for line in rules.splitlines() if "dport 443 accept" in line)
    assert "ip daddr !=" in public_https
    assert str(container_answer) not in public_https


def test_separate_vm_blocks_private_loopback_and_link_local_before_public_allow() -> None:
    rules = _separate_vm_rules(include_ipv6=True)

    for destination in ("10.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12"):
        assert destination in rules
    for destination in ("::1/128", "fc00::/7", "fe80::/10", "2001:db8::/32"):
        assert destination in rules
    assert "counter drop" in rules


def test_separate_vm_keeps_protected_host_ports_and_non_https_blocked() -> None:
    rules = _separate_vm_rules()

    assert "tcp dport { 22, 25566 } counter drop" in rules
    assert "tcp dport 80 accept" not in rules
    assert "tcp dport 25 accept" not in rules
    assert "tcp dport 443 accept" in rules
    assert "daddr { 127.0.0.53 } udp dport 53 accept" in rules
    assert "daddr { 127.0.0.53 } tcp dport 53 accept" in rules
    assert "9.9.9.9" not in rules


def test_separate_vm_rejects_destination_allowlist_inputs() -> None:
    with pytest.raises(egress.EgressError, match="destination_allowlist"):
        egress.build_rules(
            {ipaddress.ip_network("172.31.0.0/24")},
            {ipaddress.ip_address("150.171.109.196")},
            set(),
            mode=egress.SEPARATE_VM_MODE,
        )


def _refresh_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    definitions = tmp_path / "source-definitions.json"
    definitions.write_text(
        json.dumps(
            {
                "schema_version": "hermes-source-definitions-v1",
                "sources": [{"enabled": True, "url": "https://source.example.test/feed"}],
            }
        ),
        encoding="utf-8",
    )
    worker_env = tmp_path / "worker.env"
    worker_env.write_text(
        "HERMES_PROVIDER_BASE_URL=https://api.groq.com/openai/v1\n"
        "YFC_INTAKE_URL=https://app.your-fitness-coach.ru/api/v1/hermes/editorial/intake\n",
        encoding="utf-8",
    )
    resolv_conf = tmp_path / "resolv.conf"
    resolv_conf.write_text("nameserver 127.0.0.53\n", encoding="utf-8")
    return definitions, worker_env, resolv_conf


def test_separate_vm_refresh_skips_host_resolution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    definitions, worker_env, resolv_conf = _refresh_inputs(tmp_path)
    captured: dict[str, str] = {}

    def unexpected_resolution(*_: object) -> set[object]:
        pytest.fail("separate-vm must not resolve destination hosts on the host")

    monkeypatch.setattr(egress, "_resolve_hosts", unexpected_resolution)
    monkeypatch.setattr(egress, "_resolve_public", unexpected_resolution)
    monkeypatch.setattr(
        egress,
        "_network_details",
        lambda _network: ("br-abcdef123456", {ipaddress.ip_network("172.31.0.0/24")}),
    )
    monkeypatch.setattr(egress, "_apply_rules", lambda rules: captured.setdefault("rules", rules))

    result = egress.refresh(
        definitions,
        worker_env,
        "hermes-net",
        resolv_conf,
        egress.SEPARATE_VM_MODE,
    )

    assert result["deployment_mode"] == egress.SEPARATE_VM_MODE
    assert result["destination_policy"] == "public_https_after_private_destination_deny"
    assert result["resolved_addresses"] == 0
    assert "ip daddr != {" in captured["rules"]


def test_colocated_refresh_preserves_resolved_destination_allowlist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    definitions, worker_env, resolv_conf = _refresh_inputs(tmp_path)
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        egress,
        "_resolve_hosts",
        lambda _hosts: {ipaddress.ip_address("8.8.8.8")},
    )
    monkeypatch.setattr(
        egress,
        "_resolve_public",
        lambda _host: {ipaddress.ip_address("1.1.1.1")},
    )
    monkeypatch.setattr(
        egress,
        "_network_details",
        lambda _network: ("br-abcdef123456", {ipaddress.ip_network("172.31.0.0/24")}),
    )
    monkeypatch.setattr(egress, "_apply_rules", lambda rules: captured.setdefault("rules", rules))

    result = egress.refresh(
        definitions,
        worker_env,
        "hermes-net",
        resolv_conf,
        egress.COLOCATED_ISOLATED_MODE,
    )

    assert result["destination_policy"] == "resolved_destination_allowlist"
    assert "ip daddr != {" not in captured["rules"]
    assert "ip daddr { 1.1.1.1, 8.8.8.8 } tcp dport 443 accept" in captured["rules"]


@pytest.mark.parametrize(
    "mode, allow_rule",
    [
        (
            egress.SEPARATE_VM_MODE,
            "ip saddr { 172.31.0.0/24 } ip daddr != { 0.0.0.0/8 } tcp dport 443 accept",
        ),
        (
            egress.COLOCATED_ISOLATED_MODE,
            "ip saddr { 172.31.0.0/24 } ip daddr { 8.8.8.8 } tcp dport 443 accept",
        ),
    ],
)
def test_validate_understands_both_deployment_profiles(
    monkeypatch: pytest.MonkeyPatch, mode: str, allow_rule: str
) -> None:
    nft_output = "\n".join(
        [
            "table inet hermes_egress {",
            " chain forward { type filter hook forward priority -100; policy accept; }",
            " ip saddr { 172.31.0.0/24 } ct state established,related accept",
            " ip saddr { 172.31.0.0/24 } ip daddr { 127.0.0.53 } udp dport 53 accept",
            " ip saddr { 172.31.0.0/24 } ip daddr { 127.0.0.53 } tcp dport 53 accept",
            " ip saddr { 172.31.0.0/24 } ip daddr { 10.0.0.0/8 } counter drop",
            f" {allow_rule}",
            " ip saddr { 172.31.0.0/24 } counter drop",
            " input tcp dport { 22, 25566 } counter drop",
            "}",
        ]
    )
    monkeypatch.setattr(
        egress,
        "_run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, nft_output, ""),
    )

    result = egress.validate(mode)

    assert result["deployment_mode"] == mode
    assert result["drop_counters"] is True


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
