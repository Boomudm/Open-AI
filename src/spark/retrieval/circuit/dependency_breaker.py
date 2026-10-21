"""Per-factory, per-dependency RAG circuit breakers (Phase 8)."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.core.metrics import (
    circuit_outcome_dropped_total,
    rag_circuit_open,
    rag_circuit_trip_total,
)
from spark.retrieval.circuit.factory_scope import normalize_factory_id
from spark.retrieval.circuit.keys import open_key, outcome_key, probe_key
from spark.retrieval.circuit.types import (
    ALL_DEPENDENCIES,
    CRITICAL_OUTCOMES,
    OUTCOME_TO_DEPENDENCY,
    CircuitDependency,
    OutcomeKind,
)

log = get_logger(__name__)

# Legacy global key — must remain unused after Phase 8 (contract test).
LEGACY_OUTCOMES_KEY = "spark:rag:circuit:outcomes"
LEGACY_OPEN_KEY = "spark:rag:circuit:open"


def _flag_path() -> Path:
    return Path(settings.rag_circuit_flag_path)


def _read_admin_flag() -> dict[str, Any] | None:
    """Optional global admin kill-switch — not driven by traffic metrics."""
    path = _flag_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_admin_flag(*, reason: str, detail: dict[str, Any]) -> None:
    path = _flag_path()
    payload = {
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        **detail,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _delete_admin_flag() -> None:
    try:
        _flag_path().unlink(missing_ok=True)
    except OSError:
        log.warning("rag_circuit_admin_flag_delete_failed", path=str(_flag_path()))


def _window_sec() -> int:
    return max(60, int(settings.rag_circuit_window_sec or 600))


def _dependency_for_outcome(outcome: OutcomeKind) -> CircuitDependency:
    return OUTCOME_TO_DEPENDENCY[outcome]


def _set_open_gauge(factory_id: str, dependency: str, *, open_state: bool) -> None:
    rag_circuit_open.labels(factory_id=factory_id, dependency=dependency).set(
        1.0 if open_state else 0.0
    )


async def _read_open_from_redis(factory_id: str, dependency: str) -> dict[str, Any] | None:
    from spark.core.cache import Cache

    return await Cache.get().get_json(open_key(factory_id, dependency))


async def _write_open_to_redis(
    factory_id: str,
    dependency: str,
    *,
    reason: str,
    detail: dict[str, Any],
) -> None:
    from spark.core.cache import Cache

    payload = {
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        **detail,
    }
    await Cache.get().set_json(open_key(factory_id, dependency), payload, ttl=0)
    _set_open_gauge(factory_id, dependency, open_state=True)


async def _delete_open_from_redis(factory_id: str, dependency: str) -> None:
    from spark.core.cache import Cache

    await Cache.get().delete(open_key(factory_id, dependency))
    _set_open_gauge(factory_id, dependency, open_state=False)


async def is_dependency_open(factory_id: str | None, dependency: CircuitDependency) -> bool:
    fid = normalize_factory_id(factory_id)
    if await _read_open_from_redis(fid, dependency.value) is not None:
        return True
    return False


async def is_any_circuit_open_async(factory_id: str | None = None) -> bool:
    if _read_admin_flag() is not None:
        return True
    fid = normalize_factory_id(factory_id)
    for dep in ALL_DEPENDENCIES:
        if await _read_open_from_redis(fid, dep.value) is not None:
            return True
    return False


def is_rag_circuit_open() -> bool:
    """Sync check — admin flag or any open dependency for global factory."""
    if _read_admin_flag() is not None:
        return True
    try:
        return asyncio.run(is_any_circuit_open_async(None))
    except RuntimeError:
        return _read_admin_flag() is not None


async def is_rag_circuit_open_async(factory_id: str | None = None) -> bool:
    return await is_any_circuit_open_async(factory_id)


async def _outcomes_in_window(
    factory_id: str,
    dependency: CircuitDependency,
    now: float | None = None,
) -> list[OutcomeKind]:
    from spark.core.cache import Cache

    cache = Cache.get()
    key = outcome_key(factory_id, dependency.value)
    ts = now if now is not None else time.time()
    await cache.zremrangebyscore(key, float("-inf"), ts - _window_sec())
    members = await cache.zrangebyscore(key, ts - _window_sec(), ts)
    outcomes: list[OutcomeKind] = []
    for member in members:
        kind = member.split(":", 1)[0]
        if kind in CRITICAL_OUTCOMES or kind == "success":
            outcomes.append(kind)  # type: ignore[arg-type]
    return outcomes


def _rate(outcomes: list[OutcomeKind], kind: OutcomeKind) -> float:
    if not outcomes:
        return 0.0
    return sum(1 for outcome in outcomes if outcome == kind) / len(outcomes)


async def _maybe_trip(
    factory_id: str,
    dependency: CircuitDependency,
    outcomes: list[OutcomeKind],
) -> None:
    if await is_dependency_open(factory_id, dependency):
        return

    if dependency == CircuitDependency.UNHANDLED:
        unhandled = sum(1 for outcome in outcomes if outcome == "unhandled")
        threshold = int(settings.rag_circuit_unhandled_fail_threshold or 5)
        if unhandled >= threshold:
            await _trip(
                factory_id,
                dependency,
                "unhandled_failures",
                {"unhandled": unhandled, "sample_size": len(outcomes)},
            )
        return

    if len(outcomes) < 10:
        return

    if dependency == CircuitDependency.LLM:
        rate = _rate(outcomes, "llm_timeout")
        threshold = float(settings.rag_circuit_llm_timeout_rate_threshold or 0.15)
        if rate > threshold:
            await _trip(
                factory_id,
                dependency,
                "llm_timeout_rate",
                {"llm_timeout_rate": round(rate, 4), "sample_size": len(outcomes)},
            )
        return

    if dependency == CircuitDependency.EMBED:
        rate = _rate(outcomes, "embed_error")
        threshold = float(settings.rag_circuit_embed_error_rate_threshold or 0.10)
        if rate > threshold:
            await _trip(
                factory_id,
                dependency,
                "embed_error_rate",
                {"embed_error_rate": round(rate, 4), "sample_size": len(outcomes)},
            )
        return

    if dependency == CircuitDependency.RERANK:
        rate = _rate(outcomes, "rerank_gate_fail")
        threshold = float(settings.rag_circuit_rerank_gate_fail_rate_threshold or 0.25)
        if rate > threshold:
            await _trip(
                factory_id,
                dependency,
                "rerank_gate_fail_rate",
                {"rerank_gate_fail_rate": round(rate, 4), "sample_size": len(outcomes)},
            )


async def _trip(
    factory_id: str,
    dependency: CircuitDependency,
    reason: str,
    detail: dict[str, Any],
) -> None:
    await _write_open_to_redis(factory_id, dependency.value, reason=reason, detail=detail)
    rag_circuit_trip_total.labels(
        factory_id=factory_id,
        dependency=dependency.value,
        reason=reason,
    ).inc()
    log.error(
        "rag_circuit_open",
        factory_id=factory_id,
        dependency=dependency.value,
        reason=reason,
        **detail,
    )


async def allow_half_open_probe(
    factory_id: str | None,
    dependency: CircuitDependency,
) -> bool:
    from spark.core.cache import Cache

    fid = normalize_factory_id(factory_id)
    key = probe_key(fid, dependency.value)
    cache = Cache.get()
    if await cache.get_json(key):
        return False
    await cache.set_json(key, {"at": time.time()}, ttl=60)
    return True


async def record_rag_outcome_async(
    outcome: OutcomeKind,
    *,
    enabled: bool = True,
    factory_id: str | None = None,
    dependency: CircuitDependency | None = None,
    was_half_open_probe: bool = False,
) -> None:
    if not enabled:
        return

    fid = normalize_factory_id(factory_id)
    dep = dependency or _dependency_for_outcome(outcome)
    now = time.time()
    from spark.core.cache import Cache

    member = f"{outcome}:{uuid.uuid4()}"
    await Cache.get().zadd(outcome_key(fid, dep.value), {member: now})
    outcomes = await _outcomes_in_window(fid, dep, now)

    if was_half_open_probe and outcome == "success" and await is_dependency_open(fid, dep):
        await reset_rag_circuit_manual(
            factory_id=fid,
            dependency=dep.value,
            reason="half_open_probe_success",
        )
        return

    if await is_dependency_open(fid, dep):
        return
    await _maybe_trip(fid, dep, outcomes)


def record_rag_outcome(
    outcome: OutcomeKind,
    *,
    enabled: bool = True,
    factory_id: str | None = None,
    dependency: CircuitDependency | None = None,
    was_half_open_probe: bool = False,
) -> None:
    """Record outcome — critical paths prefer await via ``record_rag_outcome_async``."""
    if not enabled:
        return

    async def _run() -> None:
        try:
            await record_rag_outcome_async(
                outcome,
                enabled=True,
                factory_id=factory_id,
                dependency=dependency,
                was_half_open_probe=was_half_open_probe,
            )
        except Exception as exc:
            dep = (dependency or _dependency_for_outcome(outcome)).value
            circuit_outcome_dropped_total.labels(
                factory_id=normalize_factory_id(factory_id),
                dependency=dep,
                outcome=outcome,
            ).inc()
            log.warning(
                "rag_circuit_outcome_dropped",
                outcome=outcome,
                factory_id=normalize_factory_id(factory_id),
                dependency=dep,
                error=str(exc)[:200],
            )

    critical = outcome in CRITICAL_OUTCOMES
    try:
        loop = asyncio.get_running_loop()
        if critical:
            loop.create_task(_run())
        else:
            loop.create_task(_run())
    except RuntimeError:
        asyncio.run(_run())


async def reset_rag_circuit_manual(
    *,
    factory_id: str | None = None,
    dependency: str | None = None,
    operator: str = "",
    reason: str = "manual",
) -> bool:
    fid = normalize_factory_id(factory_id)
    from spark.core.cache import Cache

    cache = Cache.get()
    had_open = False
    deps = [dependency] if dependency else [d.value for d in ALL_DEPENDENCIES]

    admin_flag = _read_admin_flag()
    if admin_flag is not None and dependency is None and factory_id is None:
        _delete_admin_flag()
        had_open = True

    for dep in deps:
        if dep is None:
            continue
        redis_flag = await _read_open_from_redis(fid, dep)
        if redis_flag is not None:
            had_open = True
        await _delete_open_from_redis(fid, dep)
        await cache.delete(outcome_key(fid, dep))

    log.info(
        "rag_circuit_reset_manual",
        had_open_circuit=had_open,
        operator=operator or None,
        reason=reason,
        factory_id=fid,
        dependency=dependency,
        prior_admin_flag=admin_flag,
    )
    from spark.audit.worm_sink import schedule_worm_audit

    schedule_worm_audit(
        "circuit_reset",
        actor_id=operator or None,
        factory_id=fid if fid != "global" else None,
        payload={
            "reason": reason,
            "had_open_circuit": had_open,
            "dependency": dependency,
            "prior_admin_flag": admin_flag,
        },
    )
    return had_open


def reset_rag_circuit_manual_blocking(*, operator: str = "", reason: str = "manual") -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(reset_rag_circuit_manual(operator=operator, reason=reason))
    raise RuntimeError("reset_rag_circuit_manual_blocking cannot run inside a running event loop")


async def bootstrap_rag_circuit_state() -> None:
    if await is_rag_circuit_open_async():
        log.error(
            "rag_circuit_was_open_before_restart",
            admin_flag=_read_admin_flag(),
        )
        return
    log.info("rag_circuit_bootstrap", circuit_open=False)
    for dep in ALL_DEPENDENCIES:
        _set_open_gauge("global", dep.value, open_state=False)


async def get_rag_circuit_status(*, factory_id: str | None = None) -> dict[str, Any]:
    fid = normalize_factory_id(factory_id)
    dependencies: dict[str, Any] = {}
    for dep in ALL_DEPENDENCIES:
        outcomes = await _outcomes_in_window(fid, dep)
        open_flag = await _read_open_from_redis(fid, dep.value)
        dependencies[dep.value] = {
            "open": open_flag is not None,
            "sample_size": len(outcomes),
            "rates": {
                "success": round(_rate(outcomes, "success"), 4),
                "llm_timeout": round(_rate(outcomes, "llm_timeout"), 4),
                "embed_error": round(_rate(outcomes, "embed_error"), 4),
                "rerank_gate_fail": round(_rate(outcomes, "rerank_gate_fail"), 4),
                "unhandled": round(_rate(outcomes, "unhandled"), 4),
            },
            "open_detail": open_flag,
        }
    return {
        "factory_id": fid,
        "open": await is_any_circuit_open_async(fid),
        "admin_flag": _read_admin_flag(),
        "window_sec": _window_sec(),
        "dependencies": dependencies,
    }


def read_admin_flag() -> dict[str, Any] | None:
    return _read_admin_flag()


def set_maintenance_mode(*, reason: str, operator: str = "") -> None:
    _write_admin_flag(reason=reason, detail={"operator": operator})


def clear_maintenance_mode() -> None:
    _delete_admin_flag()
