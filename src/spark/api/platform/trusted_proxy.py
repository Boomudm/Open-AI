"""Client IP resolution with trusted reverse-proxy CIDRs (app-layer v2 Phase 1)."""

from __future__ import annotations

import ipaddress

from starlette.requests import Request

from spark.core.config import settings


def _parse_networks(cidrs: list[str]) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for raw in cidrs:
        text = (raw or "").strip()
        if not text:
            continue
        try:
            nets.append(ipaddress.ip_network(text, strict=False))
        except ValueError:
            continue
    return nets


def _peer_host(request: Request) -> str | None:
    if request.client and request.client.host:
        return request.client.host
    return None


def _is_trusted_peer(peer: str, networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network]) -> bool:
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(addr in net for net in networks)


def client_ip(request: Request) -> str:
    """Resolve client IP; honor X-Forwarded-For only from trusted proxy peers."""
    peer = _peer_host(request)
    networks = _parse_networks(settings.trusted_proxy_cidrs)
    forwarded = request.headers.get("x-forwarded-for", "").strip()

    if forwarded and peer and networks and _is_trusted_peer(peer, networks):
        return forwarded.split(",")[0].strip() or peer

    if peer:
        return peer
    return "unknown"
