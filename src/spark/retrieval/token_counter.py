"""Token counting backends for context budget.

Remediation v4: Thai-aware char-ratio fallback (1.8 for Thai, 2.5 for Latin).
"""

from __future__ import annotations

import re
from typing import Protocol

from spark.core.config import settings
from spark.core.logging import get_logger

log = get_logger(__name__)

_CHARS_PER_TOKEN_LATIN = 2.5
_CHARS_PER_TOKEN_THAI = 1.8
_THAI_RE = re.compile(r"[฀-๿]")


def _chars_per_token(text: str) -> float:
    if not text:
        return _CHARS_PER_TOKEN_LATIN
    thai_count = len(_THAI_RE.findall(text))
    if len(text) > 0 and thai_count / len(text) > 0.20:
        return _CHARS_PER_TOKEN_THAI
    return _CHARS_PER_TOKEN_LATIN


class TokenCounter(Protocol):
    def count(self, text: str, model: str | None = None) -> int: ...


class TiktokenCounter:
    def count(self, text: str, model: str | None = None) -> int:
        if not text:
            return 0
        try:
            import tiktoken

            encoding_name = "cl100k_base"
            if model and "gpt" in model.lower():
                try:
                    encoding_name = tiktoken.encoding_for_model(model).name
                except KeyError:
                    pass
            enc = tiktoken.get_encoding(encoding_name)
            return len(enc.encode(text))
        except Exception:
            return max(1, int(len(text) / _chars_per_token(text)))


class OllamaTokenizeCounter:
    def count(self, text: str, model: str | None = None) -> int:
        if not text:
            return 0
        try:
            import httpx

            from spark.core.config import settings as app_settings

            base = app_settings.ollama_base_url.rstrip("/")
            model_name = model or app_settings.ollama_llm_model
            with httpx.Client(timeout=5.0) as client:
                res = client.post(
                    f"{base}/api/tokenize",
                    json={"model": model_name, "prompt": text},
                )
                if res.status_code == 200:
                    tokens = res.json().get("tokens") or []
                    if tokens:
                        return len(tokens)
        except Exception as exc:
            log.debug("ollama_tokenize_fallback", error=str(exc)[:120])
        return max(1, int(len(text) / _chars_per_token(text)))


class CharRatioCounter:
    def count(self, text: str, model: str | None = None) -> int:
        _ = model
        if not text:
            return 0
        return max(1, int(len(text) / _chars_per_token(text)))


def get_token_counter() -> TokenCounter:
    backend = (settings.token_counter_backend or "auto").strip().lower()
    if backend == "tiktoken":
        return TiktokenCounter()
    if backend == "ollama":
        return OllamaTokenizeCounter()
    if backend == "char_ratio":
        return CharRatioCounter()
    # auto: tiktoken first, ollama if tiktoken fails on sample
    counter = TiktokenCounter()
    try:
        counter.count("test", None)
        return counter
    except Exception:
        return OllamaTokenizeCounter()
