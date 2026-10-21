from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from spark.core.app_profile import AppProfile

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _PROJECT_ROOT / ".env"

INSECURE_JWT_SECRETS = frozenset({"dev-secret-change-me"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.is_file() else ".env",
        extra="ignore",
        case_sensitive=False,
    )

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    # Runtime profile: test relaxes security gates for CI; production/dev are hardened (Phase 0).
    spark_profile: Literal["test", "production", "dev"] = "dev"
    # Layout PDF parser: docling (production) or fallback_pypdf (test/dev without docling).
    spark_layout_parser: Literal["docling", "fallback_pypdf"] = "fallback_pypdf"

    # PostgreSQL
    postgres_user: str = "spark"
    postgres_password: str = "sparkpass"
    postgres_db: str = "spark_db"
    postgres_host: str = "localhost"
    postgres_port: int = 5433
    db_pool_size: int = 20
    db_max_overflow: int = 30
    db_pool_recycle: int = 1800
    db_stream_pool_size: int = 10

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sql_readonly_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_sql_readonly_user}:"
            f"{self.postgres_sql_readonly_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    rag_acl_filter_mode: str = "doc_id_set"  # doc_id_set | payload_acl
    acl_cache_ttl_sec: int = 120

    # Redis
    redis_url: str = "redis://localhost:6380/0"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "spark_docs"
    qdrant_enterprise_collection: str = "spark_enterprise_docs"
    qdrant_collection_suffix_version: str = ""  # e.g. v2 for blue-green embed migration
    qdrant_shard_strategy: str = "single"  # single | per_factory | per_factory_category

    # Ollama / LLM profile (see configs/llm_profiles.yaml). Use `demo` for local dev only.
    llm_profile: str = "demo"
    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "qwen2.5:3b-instruct"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_embed_dim: int = 768
    ollama_api_key: str = ""  # OpenAI-compatible gateway key (api.kcalsion.com); blank = native Ollama
    ollama_embed_api_key: str = ""  # Optional separate key for /v1/embeddings (falls back to ollama_api_key)
    # ForgeNode (forge.kcalsion.com) — unified chat + /v1/embeddings + /v1/rerank.
    # When FORGE_BASE_URL is set, embed/rerank prefer Forge over GPU sidecar / local models.
    forge_base_url: str = ""
    forge_api_key: str = ""  # Chat/completions + /v1/models (falls back to OLLAMA_API_KEY)
    forge_embed_api_key: str = ""  # /v1/embeddings (falls back to OLLAMA_EMBED_API_KEY)
    forge_rerank_api_key: str = ""  # /v1/rerank (falls back to forge embed key)
    forge_embed_model: str = "bge-m3"
    forge_rerank_model: str = "Qwen/Qwen3-Reranker-0.6B"
    forge_timeout_sec: float = 30.0
    # Rerank fails fast (independent of the 30s client budget) so a hung remote
    # reranker degrades to the local sidecar instead of a false "no data".
    forge_rerank_timeout_sec: float = 4.0
    forge_rerank_enabled: bool = True
    # qwen3.x on the gateway emits 1000+ hidden reasoning tokens per call
    # (~13-31s each) that add nothing to grounded extraction — "none" disables
    # them and cuts LLM latency ~5x with the same answer + citation quality.
    # Set to "" / "default" to restore full reasoning. (Verified 2026-07-07.)
    # "" = don't send reasoning_effort at all (gateway/model default).
    # "none" was a latency hack for qwen3.6's 1000+ hidden think-tokens, but on
    # deepseek-v4-flash it makes some requests STALL outright (LED-status
    # replay: 3/3 timeouts at 90s with "none", 6/6 correct in 5-17s without) —
    # the production evidence-denial refusals and 45-90s first-attempt stalls
    # traced to exactly this. Set LLM_REASONING_EFFORT only for models proven
    # to need it.
    llm_reasoning_effort: str = ""
    # Use configs/retrieval/rerank_gates_forge.yaml when Forge rerank is active.
    forge_rerank_gates_path: str = ""
    # User-Agent sent on OpenAI-compatible gateway requests (api.kcalsion.com WAF allowlist).
    llm_http_user_agent: str = "spark-factory/1.0"
    ollama_llm_temperature: float = 0.1
    machinery_llm_temperature: float = 0.0
    enterprise_llm_temperature: float = 0.4
    ollama_llm_num_ctx: int = 4096

    # Ingestion
    inbox_dir: Path = Path("./data/inbox")
    raw_dir: Path = Path("./data/raw")
    documents_dir: Path = Path("./data/documents")
    machines_dir: Path = Path("./data/machines")
    max_machine_image_bytes: int = 2_097_152  # 2 MB
    profile_images_dir: Path = Path("./data/profile_images")
    max_profile_image_bytes: int = 2_097_152  # 2 MB
    feedback_dir: Path = Path("./data/feedback")
    max_feedback_photo_bytes: int = 5_242_880  # 5 MB
    max_feedback_photos: int = 3
    max_feedback_comment_chars: int = 500
    max_chat_attachment_bytes: int = 10_485_760  # 10 MB
    max_chat_attachments_per_message: int = 3
    max_chat_attachment_extract_chars: int = 8_000
    chat_attachments_dir: Path = Path("./data/chat_attachments")
    config_dir: Path = Path("./configs/ingestion")
    storage_backend: str = "local"  # local | s3
    max_upload_bytes: int = 52_428_800  # 50 MB
    ingest_temp_dir: Path = Path("/tmp/spark-ingest")
    ingest_temp_ttl_seconds: int = 3600

    # S3 / MinIO (STORAGE_BACKEND=s3)
    s3_endpoint_url: str = ""
    s3_bucket: str = "spark-documents"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "ap-southeast-1"

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "spark-v3"

    # Auth (P3) — default secure; set AUTH_REQUIRED=false in local .env for demo mode
    auth_required: bool = True
    jwt_secret: str = "dev-secret-change-me"
    cors_origins: str = "*"  # comma-separated origins in production

    # External data-source Text-to-SQL (admin-configured live analytics DB).
    # data_source_encryption_key encrypts stored external-DB passwords; empty
    # falls back to jwt_secret so no new secret is required for existing deploys.
    data_source_encryption_key: str = ""
    sql_llm_timeout_sec: float = 20.0
    sql_statement_timeout_ms: int = 15000
    external_sql_max_rows: int = 500

    # API platform (app-layer Phase 1 + v2)
    global_rate_limit_rpm: int = 600
    global_rate_limit_burst: int = 100
    http_default_timeout_sec: int = 120
    http_max_inflight_per_worker: int = 200
    trusted_proxies: str = ""  # comma-separated CIDRs; TRUSTED_PROXIES env
    security_headers_enabled: bool = True

    # Google OAuth (optional — Sign in with Google)
    google_client_id: str = ""
    google_client_secret: str = ""
    web_app_url: str = "http://127.0.0.1:3000"
    google_oauth_callback_url: str = ""
    google_oauth_allowed_domains: str = ""
    google_oauth_default_role: str = "employee"
    google_oauth_default_factory_id: str = "F-01"
    auth_token_version_cache_ttl: int = 45

    @property
    def google_oauth_allowed_domain_list(self) -> frozenset[str]:
        raw = (self.google_oauth_allowed_domains or "").strip()
        if not raw:
            return frozenset()
        return frozenset(part.lower().strip() for part in raw.split(",") if part.strip())

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @property
    def app_profile(self) -> AppProfile:
        """Application-layer profile (API gateway, auth, streaming, Redis)."""
        return AppProfile.for_env(
            app_env=self.app_env,
            spark_profile=self.spark_profile,
        )

    @property
    def effective_auth_required(self) -> bool:
        """Production always enforces auth, even if AUTH_REQUIRED is mis-set."""
        if self.is_production:
            return True
        return self.auth_required or self.app_profile.auth_required

    @property
    def jwt_secret_is_secure(self) -> bool:
        secret = (self.jwt_secret or "").strip()
        return bool(secret) and secret not in INSECURE_JWT_SECRETS

    def validate_app_profile(self) -> None:
        """Validate application-layer profile for the current environment."""
        self.app_profile.validate_for_production(
            app_env=self.app_env,
            spark_profile=self.spark_profile,
        )

    def validate_for_production(self) -> None:
        """Fail fast when production is misconfigured."""
        self.validate_profile_env()
        self.validate_app_profile()
        _is_prod_axis = self.is_production or self.spark_profile == "production"
        if not _is_prod_axis:
            return
        if not self.jwt_secret_is_secure:
            raise RuntimeError(
                "JWT_SECRET must be set to a strong, non-default value when APP_ENV=production"
            )
        if self.llm_profile.strip().lower() == "demo":
            raise RuntimeError(
                "LLM_PROFILE=demo is not allowed when APP_ENV=production — use gemma or gemma_remote"
            )
        if self.spark_profile == "test":
            raise RuntimeError(
                "SPARK_PROFILE=test is not allowed when APP_ENV=production — use production or dev"
            )
        if self.postgres_password in ("sparkpass", "spark_sql_readonly_dev", ""):
            raise RuntimeError(
                "POSTGRES_PASSWORD must be changed from default when APP_ENV=production"
            )
        if self.cors_origins.strip() == "*":
            raise RuntimeError(
                "CORS_ORIGINS must not be '*' when APP_ENV=production — "
                "set to your frontend domain (e.g. https://neo.company.com)"
            )
        if not self.trusted_proxy_cidrs:
            import warnings

            warnings.warn(
                "TRUSTED_PROXIES is empty — IP rate limiting will key on proxy IP, not client IP. "
                "Set TRUSTED_PROXIES to your load balancer CIDRs.",
                stacklevel=2,
            )

    def validate_profile_env(self) -> None:
        """Reject test-only env shortcuts outside SPARK_PROFILE=test."""
        import os

        if self.spark_profile == "test":
            return
        if os.environ.get("SPARK_SEED_SKIP_EMBED") == "1":
            raise RuntimeError(
                "SPARK_SEED_SKIP_EMBED is only allowed when SPARK_PROFILE=test "
                "(or set SPARK_PROFILE=test for CI)"
            )
        raw_llm_timeout = os.environ.get("RAG_LLM_TIMEOUT_SEC")
        if raw_llm_timeout is not None:
            try:
                if float(raw_llm_timeout) <= 0.2:
                    raise RuntimeError(
                        "RAG_LLM_TIMEOUT_SEC<=0.2 is only allowed when SPARK_PROFILE=test"
                    )
            except ValueError:
                pass

    @property
    def effective_spark_stream_live_tokens(self) -> bool:
        """Live LLM token streaming — on in production; pseudo-stream only in test profile."""
        if self.spark_profile.strip().lower() == "test":
            return bool(self.spark_stream_live_tokens)
        if self.is_production:
            return True
        if self.spark_stream_live_tokens:
            return True
        return self.app_profile.live_token_stream_default

    @property
    def effective_global_rate_limit_rpm(self) -> int:
        """Global HTTP rate limit; 0 disables (test profile / explicit off)."""
        profile_cap = self.app_profile.global_rate_limit_rpm
        if profile_cap <= 0:
            return 0
        configured = int(self.global_rate_limit_rpm or 0)
        if configured <= 0:
            return profile_cap
        return min(configured, profile_cap)

    @property
    def google_oauth_redirect_uri(self) -> str:
        if self.google_oauth_callback_url.strip():
            return self.google_oauth_callback_url.strip()
        return "http://127.0.0.1:8000/api/v1/auth/google/callback"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = (self.cors_origins or "*").strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def trusted_proxy_cidrs(self) -> list[str]:
        raw = (self.trusted_proxies or "").strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split(",") if part.strip()]

    # Authoritative reranker model (cross-encoder). The pipeline always runs:
    #   dense + lexical -> RRF fusion -> cross-encoder relevance -> absolute gate.
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_max_length: int = 1024
    # GPU inference sidecar (host py3.8 + JetPack CUDA torch). When set, dense
    # embeddings and cross-encoder rerank are offloaded to it over HTTP (~25x
    # faster than the container's CPU-only torch on this Jetson). Empty = disabled
    # = in-process CPU models (previous behavior). Set GPU_SIDECAR_REQUIRED=true
    # on Jetson production boxes to fail closed instead of loading CPU models
    # when the sidecar times out.
    gpu_sidecar_url: str = ""
    gpu_sidecar_timeout_sec: float = 15.0
    gpu_sidecar_required: bool = False
    admission_acquire_timeout_sec: float = 0.05
    # Upper bound on candidates passed to the (CPU-bound) cross-encoder reranker.
    # Caps p95 latency; never trims below top_k.
    rag_rerank_max_candidates: int = 64
    rag_retrieve_multiplier: int = 3
    rag_max_docs: int = 3
    rag_max_chunks_per_doc: int = 2
    # Multi-query retrieval: when the Thai→EN glossary expansion adds terms to a
    # query, also run the dense leg with the expanded query and fuse both lists.
    # Recovers Thai questions whose answers live in English-only manuals.
    rag_multi_query_expansion: bool = True
    # Weak-evidence continuation: a non-safety question whose candidates fail the
    # lexical evidence gate still proceeds to generation (instead of no_data) when
    # the best candidate clears this floor. Generation-side citation/verify gates
    # still decide whether the answer is shown verified, flagged, or suppressed.
    rag_weak_evidence_min_score: float = 0.15
    rag_query_embedding_cache_ttl: int = 300
    rag_llm_timeout_sec: float = 120.0  # must fit inside rag_request_budget_ms
    # One regenerate call when the gateway returns a degenerate reply or a bare
    # refusal over evidence that passed retrieval gates. Measured on the KKU
    # gateway (deepseek-v4-flash, temp 0.1): the SAME question + identical
    # retrieved context non-deterministically yields a grounded answer on one
    # run and "ไม่พบข้อมูล" (→ no_data) on the next, plus occasional 3-token
    # degenerate replies — a retry converts those from a wasted 10-50s request
    # into an answer, while genuine no-data refusals simply repeat and fall
    # through unchanged.
    rag_generation_retry_enabled: bool = True
    # Hedge cap for the FIRST generation attempt. Healthy gateway calls finish
    # well under this (deepseek-v4-flash without forced reasoning_effort:
    # 5-19s observed across the 17-18 Jul replays; max ~32s historic); a stall
    # otherwise burns the entire request budget and returns llm_unavailable
    # (observed 90s, 1 in 6 runs — and back-to-back stalls DO happen). 45s let
    # a single stall eat half the budget; 25s cuts user-visible stall cost and
    # leaves the retry ~60s of the 90s budget. Only applied when the remaining
    # budget comfortably fits two attempts.
    rag_llm_hedge_timeout_sec: float = 25.0
    context_reserved_output_tokens: int = 2048
    context_safety_margin_tokens: int = 64
    chat_history_max_turns: int = 10
    question_max_length: int = 3000
    query_compress_char_threshold: int = 500
    query_compress_profile: str = "tagging"
    token_counter_backend: str = "auto"  # auto | tiktoken | ollama | char_ratio
    router_llm_enabled: bool = False
    router_llm_confidence_threshold: float = 0.7
    router_llm_profile: str = "tagging"
    rag_circuit_flag_path: Path = Path("./data/rag/circuit_open.flag")
    rag_circuit_window_sec: int = 600
    rag_circuit_llm_timeout_rate_threshold: float = 0.15
    rag_circuit_embed_error_rate_threshold: float = 0.10
    rag_circuit_rerank_gate_fail_rate_threshold: float = 0.25
    rag_circuit_unhandled_fail_threshold: int = 5
    rag_inflight_max_per_factory: int = 50
    # Global concurrent-RAG cap across ALL factories. The LLM backend is shared,
    # so on capacity-limited hardware (e.g. a single remote gateway) letting many
    # requests pile on guarantees they all hit the request budget and time out.
    # A small global cap converts that silent 90s timeout into a fast, retryable
    # 429 (rag_at_capacity). 0 = disabled (unbounded, legacy behavior).
    rag_inflight_max_global: int = 0
    rag_query_rate_limit_per_user_min: int = 30
    rag_query_rate_limit_per_factory_min: int = 300
    # Total per-question budget. 30s assumed a fast cloud GPU — measured real
    # runs (35B gateway / Jetson-class hardware) show p95 ~120s; a budget the
    # hardware cannot meet silently drops the lexical leg and rerank on EVERY
    # question and can end in llm_unavailable even when evidence exists.
    rag_request_budget_ms: int = 150_000
    rag_lexical_budget_ms: int = 5_000
    qa_cache_enabled: bool = False
    qa_cache_ttl_days: int = 90
    semantic_cache_enabled: bool = False
    semantic_cache_threshold: float = 0.92
    semantic_cache_max_candidates: int = 50
    nli_gate_semantic_enabled: bool = True
    rag_lexical_scan_limit: int = 1500
    rag_lexical_min_score: float = 0.18
    # Postgres pg_trgm prefilter floor for lexical candidate scan (ORDER BY only).
    rag_pg_trgm_similarity_floor: float = 0.08
    # Reciprocal Rank Fusion constant. Higher k flattens the contribution of top ranks.
    rag_rrf_k: int = 60
    rag_rerank_batch_size: int = 64
    rag_rerank_timeout_sec: float = 5.0
    rag_rerank_device: str = "auto"  # auto | cpu | cuda | mps
    # Set RAG_RERANK_ENABLED=false to skip cross-encoder reranking entirely.
    # Useful on CPU/MPS dev machines where the model takes 60-90s per query.
    # Retrieval falls back to vector similarity + RRF scores without CE scoring.
    rag_rerank_enabled: bool = True
    # Test profile only — set True to skip sparse vectors for faster CI.
    sparse_vectors_disabled: bool = False

    # Ingest backend: native only (Phase 13 — legacy backends rejected at startup)
    ingest_backend: str = "native"
    # When scanned/low-text PDF pages need OCR, the parser normally dispatches an
    # async Celery task on the `ocr_heavy` queue. If the broker is unreachable or
    # no `ocr_heavy` worker is consuming, fall back to inline OCR in the current
    # worker instead of blocking for `async_timeout` (default 600s). Set
    # INGEST_OCR_INLINE_FALLBACK=false to force strict async (fail if no worker).
    ingest_ocr_inline_fallback: bool = True
    # Bounded probe (seconds) used to detect a live ocr_heavy worker before
    # dispatching. Kept short so a down broker never stalls ingestion.
    ingest_ocr_worker_probe_timeout: float = 3.0
    # Max concurrent vision-LLM calls per document during diagram-page extraction.
    # Wiring/schematic binders can have 50-150+ vector-drawing pages; without a
    # cap every flagged page fires its vision call at once, which can overwhelm
    # a GPU sidecar or trip provider rate limits.
    ingest_vision_max_concurrency: int = 4

    # Observability (Prometheus — Grafana datasource)
    prometheus_url: str = "http://localhost:9090"

    # OCR quality alerts (ingest pipeline)
    ocr_confidence_alert_min: float = 70.0
    ocr_index_min_confidence: float = 70.0
    ocr_block_job_min_confidence: float = 50.0

    # Ingest upload rate limits (Redis token bucket per factory; 0 = disabled)
    ingest_single_file_rate_limit_per_hour: int = 60
    ingest_batch_rate_limit_per_hour: int = 500

    # Index-time encode pool (Phase 5 — dedicated thread pool for dense+sparse batches)
    ingest_encode_workers: int = 0  # 0 = auto (cpu_count // 2)
    ingest_embed_batch_size: int = 32
    ingest_upsert_concurrency: int = 1

    # Profile overrides (test profile only — production uses ProductionProfile hardened defaults)
    spark_ingest_policy_enabled: bool = False
    spark_rag_circuit_enabled: bool = False
    spark_lexical_engine: Literal["postgres_thai_v3"] = "postgres_thai_v3"
    # 2.0s starved every rewrite once the gateway model spends a few seconds
    # thinking (TimeoutError surfaces as query_rewrite_llm_failed error:"") and
    # forced the rules_fallback merge on follow-ups. Healthy deepseek calls
    # land in ~5s; the rules fallback still catches genuine stalls.
    spark_query_rewrite_timeout_sec: float = 8.0
    spark_query_rewrite_max_chars: int = 256
    # Set SPARK_QUERY_REWRITE_LLM_ENABLED=false to skip the LLM rewrite step
    # (uses rule-based rewrite only). Useful on Mac dev where the 'tagging'
    # profile (local Ollama) is not available, causing JSONDecodeError noise.
    spark_query_rewrite_llm_enabled: bool = True
    # Retired compatibility setting. Generation ignores this and always uses
    # grounded LLM / structured safety paths for document answers.
    spark_extractive_first: bool = False
    spark_stream_live_tokens: bool = True
    # Stream provisional tokens for EVERY question (including safety/numeric
    # intents) instead of computing silently and replaying
    # at the end. Product decision 2026-07: operators want to see the answer
    # forming immediately; the citation-verified text still replaces the
    # provisional stream when validation completes.
    spark_stream_always_live: bool = True
    # Routing shadow-comparison mode: "shadow" schedules the agentic-vs-legacy
    # comparison logger after each answered question (currently a no-op stub —
    # see services/routing_shadow.py). Any other value skips it. The orchestrator
    # referenced this setting without it being defined, which crashed every
    # streamed answer *after* the done frame — user saw a correct answer plus a
    # spurious "ส่งคำถามไม่สำเร็จ" error banner.
    routing_mode: str = "rag"

    # Vector mirror ops (Phase 11)
    vector_drift_threshold_pct: float = 0.02

    # Test-only toggles (fail closed in production)
    spark_testing: bool = False
    allow_dummy_embeddings: bool = False

    # Insights Phase 2
    insights_hotness_threshold: float = 5.0
    insights_correlation_spike_ratio: float = 2.0
    topic_tag_confidence_min: float = 0.5
    topic_tag_batch_limit: int = 500
    topic_tag_lookback_days: int = 90


settings = Settings()
