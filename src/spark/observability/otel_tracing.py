from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator


class _NoopSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        del key, value

    def record_exception(self, exc: BaseException) -> None:
        del exc


@contextmanager
def start_span(_name: str, **_attrs: Any) -> Iterator[_NoopSpan]:
    yield _NoopSpan()


def record_span_event(_span: Any, _name: str, **_attrs: Any) -> None:
    return None


def set_span_error(_span: Any, _exc: BaseException) -> None:
    return None
