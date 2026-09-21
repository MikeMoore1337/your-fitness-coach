"""Install and validate the Task 403 Hermes-scoped nftables egress policy."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

TABLE_NAME = "hermes_egress"
CHAIN_NAME = "forward"
NETWORK_NAME = "hermes-net"
PROVIDER_HOST = "api.groq.com"
INTAKE_HOST = "app.your-fitness-coach.ru"
SCHEMA_VERSION = "hermes-source-definitions-v1"
MAX_SOURCE_HOSTS = 128
MAX_RESOLVED_ADDRESSES = 256
MAX_DNS_SERVERS = 4
NETWORK_NAME_PATTERN = re.compile(r"^hermes-[a-z0-9][a-z0-9_.-]{0,56}$")
BRIDGE_NAME_PATTERN = re.compile(r"^br-[a-f0-9]{6,64}$")
Address = ipaddress.IPv4Address | ipaddress.IPv6Address
Network = ipaddress.IPv4Network | ipaddress.IPv6Network


class EgressError(RuntimeError):
    """The scoped policy cannot be refreshed safely."""


def _run(
    args: list[str], *, check: bool = True, capture: bool = False, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        capture_output=capture,
        input=input_text,
        text=True,
        shell=False,
    )


def _clean_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def _selected_worker_values(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise EgressError("worker_env_not_regular_file")
    if sys.platform != "win32" and path.stat().st_mode & 0o777 != 0o600:
        raise EgressError("worker_env_mode_not_0600")
    wanted = {"HERMES_PROVIDER_BASE_URL", "YFC_INTAKE_URL"}
    values: dict[str, str] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            name, separator, value = raw.partition("=")
            name = name.removeprefix("export ").strip()
            if separator and name in wanted:
                values[name] = _clean_env_value(value)
    missing = sorted(name for name in wanted if not values.get(name))
    if missing:
        raise EgressError("worker_env_egress_value_missing")
    return values


def _host_from_url(value: str, *, expected: str | None = None) -> str:
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise EgressError("egress_url_not_https") from exc
    if (
        parsed.scheme.casefold() != "https"
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.query
        or port not in {None, 443}
        or not parsed.hostname
    ):
        raise EgressError("egress_url_not_https")
    host = parsed.hostname.casefold().rstrip(".")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise EgressError("egress_url_must_use_hostname")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", host):
        raise EgressError("egress_hostname_invalid")
    if expected is not None and host != expected:
        raise EgressError("egress_destination_not_approved")
    return host


def _host_value(value: object) -> str:
    if not isinstance(value, str):
        raise EgressError("source_host_invalid")
    host = value.strip().casefold().rstrip(".")
    if not host or "*" in host or ":" in host:
        raise EgressError("source_host_invalid")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise EgressError("source_host_must_use_hostname")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", host):
        raise EgressError("source_host_invalid")
    return host


def _source_hosts(path: Path) -> set[str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EgressError("source_definitions_invalid") from exc
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
        raise EgressError("source_definitions_schema_invalid")
    sources = document.get("sources")
    if not isinstance(sources, list) or not sources:
        raise EgressError("source_definitions_empty")
    hosts: set[str] = set()
    for source in sources:
        if not isinstance(source, dict) or not source.get("enabled"):
            continue
        url = source.get("url")
        if not isinstance(url, str):
            raise EgressError("source_url_invalid")
        hosts.add(_host_from_url(url))
        for field in ("allowed_redirect_hosts", "allowed_item_hosts"):
            values = source.get(field, [])
            if not isinstance(values, list):
                raise EgressError("source_host_list_invalid")
            hosts.update(_host_value(value) for value in values)
    if not hosts or len(hosts) > MAX_SOURCE_HOSTS:
        raise EgressError("source_host_count_invalid")
    return hosts


def _resolve_public(host: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    previous_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(5.0)
    try:
        try:
            results = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise EgressError("egress_host_resolution_failed") from exc
    finally:
        socket.setdefaulttimeout(previous_timeout)
    addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for _family, _socktype, _protocol, _canonname, sockaddr in results:
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except (IndexError, ValueError) as exc:
            raise EgressError("egress_resolution_invalid") from exc
        if not address.is_global:
            raise EgressError("egress_resolution_not_global")
        addresses.add(address)
    if not addresses:
        raise EgressError("egress_resolution_empty")
    return addresses


def _resolve_hosts(hosts: set[str]) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for host in sorted(hosts):
        addresses.update(_resolve_public(host))
        if len(addresses) > MAX_RESOLVED_ADDRESSES:
            raise EgressError("egress_resolution_count_invalid")
    return addresses


def _dns_servers(path: Path) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EgressError("dns_configuration_unreadable") from exc
    servers: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for line in lines:
        value = line.split("#", 1)[0].strip()
        if not value.startswith("nameserver "):
            continue
        address_text = value.removeprefix("nameserver ").strip()
        try:
            servers.add(ipaddress.ip_address(address_text))
        except ValueError as exc:
            raise EgressError("dns_server_invalid") from exc
        if len(servers) > MAX_DNS_SERVERS:
            raise EgressError("dns_server_count_invalid")
    if not servers:
        raise EgressError("dns_server_missing")
    return servers


def _network_details(network: str) -> tuple[str, set[Network]]:
    if NETWORK_NAME_PATTERN.fullmatch(network) is None:
        raise EgressError("hermes_network_invalid")
    result = _run(["docker", "network", "inspect", network], capture=True)
    try:
        documents = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise EgressError("hermes_network_inspection_invalid") from exc
    if not isinstance(documents, list) or len(documents) != 1 or not isinstance(documents[0], dict):
        raise EgressError("hermes_network_inspection_invalid")
    document = documents[0]
    if document.get("Driver") != "bridge":
        raise EgressError("hermes_network_driver_invalid")
    containers = document.get("Containers") or {}
    if not isinstance(containers, dict):
        raise EgressError("hermes_network_containers_invalid")
    for container in containers.values():
        if not isinstance(container, dict):
            raise EgressError("hermes_network_containers_invalid")
        name = str(container.get("Name", ""))
        if "fit-mini-app" in name or not name.startswith("hermes-"):
            raise EgressError("hermes_network_has_unapproved_container")
    options = document.get("Options") or {}
    bridge = options.get("com.docker.network.bridge.name")
    if not isinstance(bridge, str) or not bridge:
        network_id = document.get("Id")
        if not isinstance(network_id, str) or len(network_id) < 6:
            raise EgressError("hermes_network_id_invalid")
        bridge = f"br-{network_id[:12]}"
    if BRIDGE_NAME_PATTERN.fullmatch(bridge) is None:
        raise EgressError("hermes_bridge_invalid")
    subnets: set[Network] = set()
    for config in (document.get("IPAM") or {}).get("Config", []):
        if not isinstance(config, dict) or not isinstance(config.get("Subnet"), str):
            continue
        try:
            subnets.add(ipaddress.ip_network(config["Subnet"], strict=False))
        except ValueError as exc:
            raise EgressError("hermes_subnet_invalid") from exc
    if not subnets:
        raise EgressError("hermes_subnet_missing")
    names_result = _run(["docker", "network", "ls", "--format", "{{.Name}}"], capture=True)
    for other in names_result.stdout.splitlines():
        if other == network:
            continue
        other_result = _run(["docker", "network", "inspect", other], capture=True)
        try:
            other_documents = json.loads(other_result.stdout)
        except json.JSONDecodeError as exc:
            raise EgressError("docker_network_inspection_invalid") from exc
        for other_document in other_documents:
            if not isinstance(other_document, dict):
                raise EgressError("docker_network_inspection_invalid")
            for config in (other_document.get("IPAM") or {}).get("Config", []):
                if not isinstance(config, dict) or not isinstance(config.get("Subnet"), str):
                    continue
                try:
                    other_subnet = ipaddress.ip_network(config["Subnet"], strict=False)
                except ValueError as exc:
                    raise EgressError("docker_subnet_invalid") from exc
                if any(subnet.overlaps(other_subnet) for subnet in subnets):
                    raise EgressError("hermes_subnet_overlaps_docker_network")
    return bridge, subnets


def _elements(values: set[Address]) -> str:
    return ", ".join(sorted(str(value) for value in values))


def build_rules(
    subnets: set[Network],
    allowed_addresses: set[Address],
    dns_servers: set[Address],
) -> str:
    if not subnets:
        raise EgressError("hermes_subnet_missing")
    source_v4 = {value for value in subnets if value.version == 4}
    source_v6 = {value for value in subnets if value.version == 6}
    allowed_v4 = {value for value in allowed_addresses if value.version == 4}
    allowed_v6 = {value for value in allowed_addresses if value.version == 6}
    dns_v4 = {value for value in dns_servers if value.version == 4}
    dns_v6 = {value for value in dns_servers if value.version == 6}
    lines = [
        f"add table inet {TABLE_NAME}",
        f"add chain inet {TABLE_NAME} {CHAIN_NAME} {{ type filter hook forward priority -100; policy accept; }}",
    ]
    if source_v4:
        source = _elements(source_v4)
        lines.extend(
            [
                f"add rule inet {TABLE_NAME} {CHAIN_NAME} ip saddr {{ {source} }} ct state invalid drop",
                f"add rule inet {TABLE_NAME} {CHAIN_NAME} ip saddr {{ {source} }} ct state established,related accept",
                f"add rule inet {TABLE_NAME} {CHAIN_NAME} ip daddr {{ {source} }} ct state established,related accept",
            ]
        )
    if source_v6:
        source = _elements(source_v6)
        lines.extend(
            [
                f"add rule inet {TABLE_NAME} {CHAIN_NAME} ip6 saddr {{ {source} }} ct state invalid drop",
                f"add rule inet {TABLE_NAME} {CHAIN_NAME} ip6 saddr {{ {source} }} ct state established,related accept",
                f"add rule inet {TABLE_NAME} {CHAIN_NAME} ip6 daddr {{ {source} }} ct state established,related accept",
            ]
        )
    if dns_v4:
        dns = _elements(dns_v4)
        if source_v4:
            source = _elements(source_v4)
            lines.extend(
                [
                    f"add rule inet {TABLE_NAME} {CHAIN_NAME} ip saddr {{ {source} }} ip daddr {{ {dns} }} udp dport 53 accept",
                    f"add rule inet {TABLE_NAME} {CHAIN_NAME} ip saddr {{ {source} }} ip daddr {{ {dns} }} tcp dport 53 accept",
                ]
            )
    if dns_v6:
        dns = _elements(dns_v6)
        if source_v6:
            source = _elements(source_v6)
            lines.extend(
                [
                    f"add rule inet {TABLE_NAME} {CHAIN_NAME} ip6 saddr {{ {source} }} ip6 daddr {{ {dns} }} udp dport 53 accept",
                    f"add rule inet {TABLE_NAME} {CHAIN_NAME} ip6 saddr {{ {source} }} ip6 daddr {{ {dns} }} tcp dport 53 accept",
                ]
            )
    source_v4_text = _elements(source_v4)
    source_v6_text = _elements(source_v6)
    if source_v4:
        lines.append(
            f"add rule inet {TABLE_NAME} {CHAIN_NAME} ip saddr {{ {source_v4_text} }} ip daddr {{ 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.0.0.0/24, 192.0.2.0/24, 192.168.0.0/16, 198.18.0.0/15, 198.51.100.0/24, 203.0.113.0/24, 224.0.0.0/4, 240.0.0.0/4 }} drop"
        )
    if source_v6:
        lines.append(
            f"add rule inet {TABLE_NAME} {CHAIN_NAME} ip6 saddr {{ {source_v6_text} }} ip6 daddr {{ ::/128, ::1/128, ::ffff:0:0/96, 100::/64, 2001:db8::/32, fc00::/7, fe80::/10, ff00::/8 }} drop"
        )
    if allowed_v4:
        if source_v4:
            lines.append(
                f"add rule inet {TABLE_NAME} {CHAIN_NAME} ip saddr {{ {source_v4_text} }} ip daddr {{ {_elements(allowed_v4)} }} tcp dport 443 accept"
            )
    if allowed_v6:
        if source_v6:
            lines.append(
                f"add rule inet {TABLE_NAME} {CHAIN_NAME} ip6 saddr {{ {source_v6_text} }} ip6 daddr {{ {_elements(allowed_v6)} }} tcp dport 443 accept"
            )
    if source_v4:
        lines.append(
            f"add rule inet {TABLE_NAME} {CHAIN_NAME} ip saddr {{ {source_v4_text} }} drop"
        )
    if source_v6:
        lines.append(
            f"add rule inet {TABLE_NAME} {CHAIN_NAME} ip6 saddr {{ {source_v6_text} }} drop"
        )
    return "\n".join(lines) + "\n"


def _table_exists() -> bool:
    result = _run(["nft", "list", "table", "inet", TABLE_NAME], check=False, capture=True)
    return result.returncode == 0


def _apply_rules(rules: str) -> None:
    prefix = f"destroy table inet {TABLE_NAME}\n" if _table_exists() else ""
    _run(["nft", "-f", "-"], input_text=prefix + rules)


def refresh(
    definitions: Path, worker_env: Path, network: str, resolv_conf: Path
) -> dict[str, object]:
    values = _selected_worker_values(worker_env)
    source_hosts = _source_hosts(definitions)
    source_hosts.add(_host_from_url(values["HERMES_PROVIDER_BASE_URL"], expected=PROVIDER_HOST))
    source_hosts.add(_host_from_url(values["YFC_INTAKE_URL"], expected=INTAKE_HOST))
    addresses = _resolve_hosts(source_hosts)
    dns_servers = _dns_servers(resolv_conf)
    bridge, subnets = _network_details(network)
    _apply_rules(build_rules(subnets, addresses, dns_servers))
    return {
        "status": "refreshed",
        "table": TABLE_NAME,
        "bridge": bridge,
        "allowed_destinations": len(source_hosts),
        "resolved_addresses": len(addresses),
        "dns_servers": len(dns_servers),
        "default_deny": True,
        "secrets_logged": False,
    }


def validate() -> dict[str, object]:
    result = _run(["nft", "list", "table", "inet", TABLE_NAME], check=False, capture=True)
    if result.returncode != 0:
        raise EgressError("hermes_egress_table_missing")
    lines = result.stdout.splitlines()
    required = (
        "hook forward",
        "policy accept",
        "ct state established,related",
    )
    if any(value not in result.stdout for value in required):
        raise EgressError("hermes_egress_policy_incomplete")
    if not any("ip saddr" in line and " drop" in line for line in lines):
        raise EgressError("hermes_egress_default_deny_missing")
    if not any("dport 443" in line for line in lines) or not any(
        "dport 53" in line for line in lines
    ):
        raise EgressError("hermes_egress_allowlist_missing")
    if any("tcp dport 443 accept" in line and " daddr " not in line for line in lines) or any(
        "dport 53 accept" in line and " daddr " not in line for line in lines
    ):
        raise EgressError("hermes_egress_policy_incomplete")
    return {"status": "validated", "table": TABLE_NAME, "default_deny": True}


def remove() -> dict[str, object]:
    if _table_exists():
        _run(["nft", "delete", "table", "inet", TABLE_NAME])
    return {"status": "removed", "table": TABLE_NAME}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    refresh_parser = subparsers.add_parser("refresh")
    refresh_parser.add_argument("--definitions", type=Path, required=True)
    refresh_parser.add_argument("--worker-env", type=Path, required=True)
    refresh_parser.add_argument("--network", default=NETWORK_NAME)
    refresh_parser.add_argument("--resolv-conf", type=Path, default=Path("/etc/resolv.conf"))
    subparsers.add_parser("validate")
    subparsers.add_parser("remove")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "refresh":
            result = refresh(args.definitions, args.worker_env, args.network, args.resolv_conf)
        elif args.command == "validate":
            result = validate()
        else:
            result = remove()
    except EgressError, OSError, subprocess.CalledProcessError:
        print(
            json.dumps({"error": "hermes_egress_failed", "secrets_logged": False}), file=sys.stderr
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
