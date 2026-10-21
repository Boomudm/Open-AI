from __future__ import annotations

from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


class _LazySingleton(Generic[T]):
    __slots__ = ("_factory", "_instance")

    def __init__(self, factory: Callable[[], T]) -> None:
        object.__setattr__(self, "_factory", factory)
        object.__setattr__(self, "_instance", None)

    def _get(self) -> T:
        inst = object.__getattribute__(self, "_instance")
        if inst is None:
            inst = object.__getattribute__(self, "_factory")()
            object.__setattr__(self, "_instance", inst)
        return inst

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get(), name)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._get()(*args, **kwargs)


def lazy_singleton(factory: Callable[[], T]) -> T:
    """Defer ``factory()`` until the first attribute access or call."""
    return _LazySingleton(factory)  # type: ignore[return-value]
