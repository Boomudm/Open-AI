#!/usr/bin/env python3
"""App-layer load smoke — concurrent health probes and SSE/REST mix (Phase 12).

Usage (API reachable on LAN):
  uv run python scripts/load/app_layer_smoke.py --base-url http://spark.lan
  uv run python scripts/load/app_layer_smoke.py --base-url http://localhost:8000 --scenario sse-rest
  SMOKE_BEARER_TOKEN=... uv run python scripts/load/app_layer_smoke.py --scenario ticket-mint
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time

import httpx

DEFAULT_REQUESTS = 50
DEFAULT_CONCURRENCY = 20
DEFAULT_P95_MS = 500.0
DEFAULT_SSE_CONNECTIONS = 100
DEFAULT_REST_CONCURRENCY = 20
DEFAULT_TICKET_MINTS = 50


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((pct / 100.0) * (len(ordered) - 1)))
    return ordered[max(0, min(idx, len(ordered) - 1))]


async def _probe(client: httpx.AsyncClient, url: str) -> tuple[int, float]:
    start = time.perf_counter()
    try:
        res = await client.get(url)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return res.status_code, elapsed_ms
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return 0, elapsed_ms


async def _hold_sse_connection(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    hold_sec: float,
) -> bool:
    try:
        async with client.stream("GET", url, headers=headers) as response:
            deadline = time.perf_counter() + hold_sec
            async for _chunk in response.aiter_bytes():
                if time.perf_counter() >= deadline:
                    break
        return response.status_code in {200, 429}
    except Exception:
        return False


async def run_healthz_smoke(
    base_url: str,
    *,
    requests: int,
    concurrency: int,
    p95_ms: float,
) -> int:
    health_url = f"{base_url.rstrip('/')}/healthz"
    ready_url = f"{base_url.rstrip('/')}/readyz?lite=1"
    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    failures = 0

    async with httpx.AsyncClient(timeout=10.0) as client:
        ready_res = await client.get(ready_url)
        if ready_res.status_code != 200:
            print(
                f"readyz not healthy ({ready_res.status_code}) — fix dependencies before load smoke",
                file=sys.stderr,
            )
            return 1

        async def one() -> None:
            nonlocal failures
            async with sem:
                status, ms = await _probe(client, health_url)
                latencies.append(ms)
                if status != 200:
                    failures += 1

        await asyncio.gather(*(one() for _ in range(requests)))

    p50 = statistics.median(latencies) if latencies else 0.0
    p95 = _percentile(latencies, 95)
    print(f"scenario=healthz requests={requests} concurrency={concurrency} failures={failures}")
    print(f"healthz latency ms: p50={p50:.1f} p95={p95:.1f} (threshold p95<{p95_ms:.0f})")

    if failures:
        print("FAIL: one or more /healthz requests failed", file=sys.stderr)
        return 1
    if p95 > p95_ms:
        print(f"FAIL: p95 {p95:.1f}ms exceeds {p95_ms:.0f}ms", file=sys.stderr)
        return 1
    print("OK")
    return 0


async def run_sse_rest_mix(
    base_url: str,
    *,
    sse_count: int,
    rest_concurrency: int,
    rest_rounds: int,
    bearer_token: str | None,
    hold_sec: float,
) -> int:
    root = base_url.rstrip("/")
    health_url = f"{root}/healthz"
    sse_url = f"{root}/api/v1/alerts/stream"
    headers: dict[str, str] = {}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    rest_failures = 0
    rest_503 = 0
    sse_opened = 0

    async with httpx.AsyncClient(timeout=None) as client:
        ready_res = await client.get(f"{root}/readyz?lite=1")
        if ready_res.status_code != 200:
            print(f"readyz not healthy ({ready_res.status_code})", file=sys.stderr)
            return 1

        async def hold_one() -> None:
            nonlocal sse_opened
            if await _hold_sse_connection(
                client, sse_url, headers=headers, hold_sec=hold_sec
            ):
                sse_opened += 1

        sse_tasks = [asyncio.create_task(hold_one()) for _ in range(sse_count)]
        await asyncio.sleep(0.5)

        sem = asyncio.Semaphore(rest_concurrency)

        async def rest_burst() -> None:
            nonlocal rest_failures, rest_503
            async with sem:
                status, _ = await _probe(client, health_url)
                if status != 200:
                    rest_failures += 1
                if status == 503:
                    rest_503 += 1

        for _ in range(rest_rounds):
            await asyncio.gather(*(rest_burst() for _ in range(rest_concurrency)))

        for task in sse_tasks:
            task.cancel()
        await asyncio.gather(*sse_tasks, return_exceptions=True)

    print(
        f"scenario=sse-rest sse_target={sse_count} sse_opened={sse_opened} "
        f"rest_rounds={rest_rounds} rest_concurrency={rest_concurrency} "
        f"rest_failures={rest_failures} rest_503={rest_503}"
    )
    if rest_503:
        print("FAIL: REST probes returned 503 while SSE connections active", file=sys.stderr)
        return 1
    if rest_failures:
        print("FAIL: REST probes failed while SSE connections active", file=sys.stderr)
        return 1
    if bearer_token and sse_opened < min(5, sse_count // 10):
        print(
            f"WARN: only {sse_opened} SSE connections held (token may lack factory scope)",
            file=sys.stderr,
        )
    print("OK")
    return 0


async def run_ticket_mint_smoke(
    base_url: str,
    *,
    mints: int,
    concurrency: int,
    bearer_token: str | None,
) -> int:
    if not bearer_token:
        print("SKIP ticket-mint: set SMOKE_BEARER_TOKEN or --bearer-token", file=sys.stderr)
        return 0

    root = base_url.rstrip("/")
    url = f"{root}/api/v1/streams/ticket"
    headers = {"Authorization": f"Bearer {bearer_token}"}
    failures = 0
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(timeout=15.0) as client:

        async def mint_one() -> None:
            nonlocal failures
            async with sem:
                try:
                    res = await client.post(url, headers=headers, json={"channel": "chat_ask"})
                    if res.status_code not in {200, 429}:
                        failures += 1
                except Exception:
                    failures += 1

        await asyncio.gather(*(mint_one() for _ in range(mints)))

    print(f"scenario=ticket-mint mints={mints} concurrency={concurrency} failures={failures}")
    if failures:
        print("FAIL: stream ticket mint errors", file=sys.stderr)
        return 1
    print("OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="App-layer HTTP load smoke")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--scenario",
        choices=("healthz", "sse-rest", "ticket-mint", "all"),
        default="healthz",
    )
    parser.add_argument("--requests", type=int, default=DEFAULT_REQUESTS)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--p95-ms", type=float, default=DEFAULT_P95_MS)
    parser.add_argument("--sse-count", type=int, default=DEFAULT_SSE_CONNECTIONS)
    parser.add_argument("--rest-concurrency", type=int, default=DEFAULT_REST_CONCURRENCY)
    parser.add_argument("--rest-rounds", type=int, default=3)
    parser.add_argument("--sse-hold-sec", type=float, default=8.0)
    parser.add_argument("--ticket-mints", type=int, default=DEFAULT_TICKET_MINTS)
    parser.add_argument(
        "--bearer-token",
        default=os.environ.get("SMOKE_BEARER_TOKEN"),
        help="JWT for SSE/ticket scenarios (or SMOKE_BEARER_TOKEN env)",
    )
    args = parser.parse_args(argv)

    async def _run() -> int:
        rc = 0
        if args.scenario in {"healthz", "all"}:
            rc = await run_healthz_smoke(
                args.base_url,
                requests=args.requests,
                concurrency=args.concurrency,
                p95_ms=args.p95_ms,
            )
            if rc != 0:
                return rc
        if args.scenario in {"sse-rest", "all"}:
            rc = await run_sse_rest_mix(
                args.base_url,
                sse_count=args.sse_count,
                rest_concurrency=args.rest_concurrency,
                rest_rounds=args.rest_rounds,
                bearer_token=args.bearer_token,
                hold_sec=args.sse_hold_sec,
            )
            if rc != 0:
                return rc
        if args.scenario in {"ticket-mint", "all"}:
            rc = await run_ticket_mint_smoke(
                args.base_url,
                mints=args.ticket_mints,
                concurrency=args.concurrency,
                bearer_token=args.bearer_token,
            )
        return rc

    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
