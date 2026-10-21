"""SSE connection registry — delegates to enforced governor (v2 Phase 3)."""

from __future__ import annotations

from spark.services.streams.connection_governor import connection_governor


class ConnectionRegistry:
    """Backward-compatible facade over :data:`connection_governor`."""

    def register(self, *, user_id: str, channel: str) -> None:
        result = connection_governor.try_acquire(user_id=user_id, channel=channel)
        if not result.ok:
            from spark.services.streams.connection_governor import raise_sse_connection_limit

            raise_sse_connection_limit(reason=result.status, channel=channel)

    def unregister(self, *, user_id: str, channel: str) -> None:
        connection_governor.release(user_id=user_id, channel=channel)

    @property
    def active_total(self) -> int:
        return connection_governor.active_total


connection_registry = ConnectionRegistry()
