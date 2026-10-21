"""Unified LLM client — routes via configs/llm_profiles.yaml (Ollama or vLLM OpenAI API)."""

from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from spark.core.config import settings
from spark.core.llm_profile import load_llm_profile
from spark.core.logging import get_logger

log = get_logger(__name__)

_DEFAULT_GATEWAY_USER_AGENT = "spark-factory/1.0"


def openai_gateway_headers() -> dict[str, str]:
    """HTTP headers for OpenAI-compatible gateway clients (WAF allowlist on api.kcalsion.com).

    LangChain/httpx defaults are blocked by the gateway; curl/8.5.0 is known-good.
    Override via ``LLM_HTTP_USER_AGENT`` (e.g. during WAF allowlist rollout).
    """
    user_agent = (settings.llm_http_user_agent or _DEFAULT_GATEWAY_USER_AGENT).strip()
    return {
        "User-Agent": user_agent,
        "Accept": "application/json",
    }


def _reasoning_extra_body() -> dict[str, object]:
    """Request-body override for the gateway model's hidden reasoning.

    Off by default. ``none`` was a latency hack for qwen3.x's 1000+ <think>
    tokens (~13-31s/call), but on deepseek-v4-flash it makes some requests
    stall until timeout and others come back as evidence-denying refusals
    (17 Jul replay: LED case 3/3 stalls with "none", 6/6 correct without).
    Returns an empty dict (no override) when the setting is blank/"default".
    """
    effort = (getattr(settings, "llm_reasoning_effort", "") or "").strip().lower()
    if not effort or effort == "default":
        return {}
    return {"extra_body": {"reasoning_effort": effort}}


@lru_cache(maxsize=4)
def get_chat_llm(profile_name: str | None = None) -> BaseChatModel:
    """Return a cached LangChain chat model for the active LLM profile."""
    try:
        profile = load_llm_profile(profile_name)
    except (KeyError, ValueError):
        profile = {}

    provider = str(profile.get("provider", "ollama")).lower()
    temperature = float(profile.get("temperature", settings.ollama_llm_temperature))
    num_ctx = int(profile.get("num_ctx", settings.ollama_llm_num_ctx))
    model = profile.get("llm_model") or settings.ollama_llm_model
    base_url = profile.get("base_url") or settings.ollama_base_url

    if provider in ("vllm", "openai"):
        api_base = base_url.rstrip("/")
        if not api_base.endswith("/v1"):
            api_base = f"{api_base}/v1"
        gateway_headers = openai_gateway_headers()
        log.debug(
            "llm_client_vllm",
            model=model,
            base_url=api_base,
            user_agent=gateway_headers.get("User-Agent"),
        )
        return ChatOpenAI(
            model=model,
            base_url=api_base,
            api_key=profile.get("api_key") or settings.ollama_api_key or "spark-local",
            temperature=temperature,
            max_tokens=int(profile.get("max_tokens", 2048)),
            default_headers=gateway_headers,
            stream_usage=True,
            # This box's path to the remote gateway is intermittently flaky
            # ("All connection attempts failed" — observed recurring across
            # query rewrite, session titling, and main generation, all
            # succeeding again seconds later on a bare retry). Without an
            # explicit retry count here the request surfaces that single
            # transient blip straight to the user as "AI unavailable" instead
            # of quietly recovering within the existing 60s request budget.
            max_retries=3,
            **_reasoning_extra_body(),
        )

    log.debug("llm_client_ollama", model=model, base_url=base_url)
    return ChatOllama(
        base_url=base_url,
        model=model,
        temperature=temperature,
        num_ctx=num_ctx,
    )


@lru_cache(maxsize=4)
def get_pipeline_llm(pipeline: str) -> BaseChatModel:
    """Return a chat model with pipeline-specific temperature override."""
    if pipeline == "machinery":
        temperature = settings.machinery_llm_temperature
    elif pipeline == "enterprise":
        temperature = settings.enterprise_llm_temperature
    else:
        return get_chat_llm()

    try:
        profile = load_llm_profile()
    except (KeyError, ValueError):
        profile = {}

    provider = str(profile.get("provider", "ollama")).lower()
    num_ctx = int(profile.get("num_ctx", settings.ollama_llm_num_ctx))
    model = profile.get("llm_model") or settings.ollama_llm_model
    base_url = profile.get("base_url") or settings.ollama_base_url

    if provider in ("vllm", "openai"):
        api_base = base_url.rstrip("/")
        if not api_base.endswith("/v1"):
            api_base = f"{api_base}/v1"
        gateway_headers = openai_gateway_headers()
        return ChatOpenAI(
            model=model,
            base_url=api_base,
            api_key=profile.get("api_key") or settings.ollama_api_key or "spark-local",
            temperature=temperature,
            max_tokens=int(profile.get("max_tokens", 2048)),
            default_headers=gateway_headers,
            stream_usage=True,
            max_retries=3,
            **_reasoning_extra_body(),
        )

    return ChatOllama(
        base_url=base_url,
        model=model,
        temperature=temperature,
        num_ctx=num_ctx,
    )


def reset_llm_cache() -> None:
    get_chat_llm.cache_clear()
    get_pipeline_llm.cache_clear()
