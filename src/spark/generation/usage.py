# -*- coding: utf-8 -*-
"""LLM token usage normalization.

LangChain providers expose usage in slightly different shapes. Keep the
request-facing shape stable so chat persistence and dashboards can aggregate it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _model_name(llm: Any) -> str | None:
    for attr in ("model_name", "model", "model_id"):
        value = getattr(llm, attr, None)
        if value:
            return str(value)
    return None


def _provider(llm: Any) -> str:
    name = llm.__class__.__name__.lower()
    if "openai" in name:
        return "openai"
    if "ollama" in name:
        return "ollama"
    return name or "unknown"


def _usage_mapping(obj: Any) -> Mapping[str, Any] | None:
    direct = getattr(obj, "usage_metadata", None)
    if isinstance(direct, Mapping):
        return direct

    response_meta = getattr(obj, "response_metadata", None)
    if isinstance(response_meta, Mapping):
        for key in ("token_usage", "usage"):
            nested = response_meta.get(key)
            if isinstance(nested, Mapping):
                return nested
        if any(k in response_meta for k in ("prompt_tokens", "completion_tokens", "total_tokens")):
            return response_meta

    additional = getattr(obj, "additional_kwargs", None)
    if isinstance(additional, Mapping):
        nested = additional.get("usage")
        if isinstance(nested, Mapping):
            return nested

    return None


def normalize_llm_usage(obj: Any, *, llm: Any, operation: str) -> dict[str, Any] | None:
    raw = _usage_mapping(obj)
    if not raw:
        return None

    prompt = _as_int(
        raw.get("input_tokens")
        or raw.get("prompt_tokens")
        or raw.get("prompt_eval_count")
    )
    completion = _as_int(
        raw.get("output_tokens")
        or raw.get("completion_tokens")
        or raw.get("eval_count")
    )
    total = _as_int(raw.get("total_tokens") or (prompt + completion))
    if total <= 0 and prompt <= 0 and completion <= 0:
        return None

    return {
        "provider": _provider(llm),
        "model": _model_name(llm),
        "operation": operation,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total or (prompt + completion),
        "raw": dict(raw),
    }


def record_llm_usage(target: Any, obj: Any, *, llm: Any, operation: str) -> None:
    usage = normalize_llm_usage(obj, llm=llm, operation=operation)
    if not usage:
        return
    calls = getattr(target, "llm_usage_calls", None)
    if calls is None:
        calls = []
        setattr(target, "llm_usage_calls", calls)
    calls.append(usage)


def summarize_llm_usage(calls: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not calls:
        return None
    prompt = sum(_as_int(c.get("prompt_tokens")) for c in calls)
    completion = sum(_as_int(c.get("completion_tokens")) for c in calls)
    total = sum(_as_int(c.get("total_tokens")) for c in calls) or prompt + completion
    providers = sorted({str(c.get("provider")) for c in calls if c.get("provider")})
    models = sorted({str(c.get("model")) for c in calls if c.get("model")})
    return {
        "source": "provider",
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "providers": providers,
        "models": models,
        "calls": calls,
    }
