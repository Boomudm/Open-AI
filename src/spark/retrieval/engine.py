"""Retrieval engine — intent routing, vector+lexical fusion, degradation report (Phase 5)."""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Protocol

from spark.core.config import settings
from spark.core.database import AsyncSessionLocal
from spark.core.metrics import rag_embed_error_total, rag_lexical_degraded_total, rag_retrieval_leg_seconds
from spark.core.production_profile import LexicalEngine, RemediationFlags
from spark.retrieval.candidates import hydrate_parent_content_from_pg, retrieval_identity
from spark.retrieval.degradation import RetrievalReport, build_retrieval_report
from spark.retrieval.fusion import fuse_candidates
from spark.retrieval.fusion_weights import resolve_hybrid_weights
from spark.retrieval.intent.glossary import expand_lexical_variants
from spark.retrieval.deadline import RequestDeadline
from spark.retrieval.intent.apply import apply_intent_boosts, apply_intent_to_filter
from spark.retrieval.intent.router import IntentPlan, IntentRouter
from spark.retrieval.intent.types import QueryIntent
from spark.retrieval.exact import retrieve_exact_evidence_candidates
from spark.retrieval.lexical.tokenize_industrial import extract_plc_tags
from spark.retrieval.logging.features import log_retrieval_features
from spark.retrieval.vector.qdrant_search import search_qdrant_exact_tag, search_qdrant_hybrid
from spark.core.qdrant import ensure_collection, get_async_qdrant_client
from spark.retrieval.common import log
from spark.retrieval.models import RAGFilter, RetrievedDoc
from spark.retrieval.scoring import _retrieval_sources_from_docs
from spark.retrieval.tuning import FusionMethod, RagFusionConfig

CANDIDATE_POOL_LIMIT = 64
_MIN_LLM_BUDGET_MS = 8000

# Fusion architecture (Phase 5):
# - Qdrant may fuse dense+sparse internally (single vector leg output).
# - Application fusion merges exactly two legs: vector_leg + lexical_leg (one RRF call).


class RerankFn(Protocol):
    async def __call__(
        self,
        query: str,
        docs: list[RetrievedDoc],
        top_k: int,
        *,
        session_id: str | None = None,
        intent_plan: IntentPlan | None = None,
        deadline: RequestDeadline | None = None,
    ) -> list[RetrievedDoc]: ...


class RetrievalEngine:
    """Single retrieval orchestrator — replaces RetrievalMixin + HybridRetrievalMixin."""

    def __init__(
        self,
        *,
        embedder: Any,
        intent_router: IntentRouter | None = None,
        resolve_fusion_config: Callable[[RAGFilter], Awaitable[RagFusionConfig]] | None = None,
        resolve_lexical_engine: Callable[[RAGFilter], Awaitable[LexicalEngine]] | None = None,
        apply_rerank: RerankFn | None = None,
    ) -> None:
        self.embedder = embedder
        self.intent_router = intent_router or IntentRouter()
        self._resolve_fusion_config = resolve_fusion_config
        self._resolve_lexical_engine = resolve_lexical_engine
        self._apply_rerank = apply_rerank
        self.last_report: RetrievalReport | None = None
        self.last_intent_plan: IntentPlan | None = None

    async def resolve_lexical_engine(self, rf: RAGFilter) -> LexicalEngine:
        if self._resolve_lexical_engine is not None:
            return await self._resolve_lexical_engine(rf)
        flags = RemediationFlags.from_settings()
        if rf.factory_id:
            from spark.services.factory_config_service import factory_config_service

            async with AsyncSessionLocal() as session:
                factory_cfg = await factory_config_service.resolve(session, rf.factory_id)
            flags = RemediationFlags.for_factory(factory_cfg)
        return flags.lexical_engine

    async def resolve_fusion_config(self, rf: RAGFilter) -> RagFusionConfig:
        if self._resolve_fusion_config is not None:
            return await self._resolve_fusion_config(rf)
        if not rf.factory_id:
            return RagFusionConfig.from_factory_config({})
        from spark.services.factory_config_service import factory_config_service

        async with AsyncSessionLocal() as session:
            factory_cfg = await factory_config_service.resolve(session, rf.factory_id)
        return RagFusionConfig.from_factory_config(factory_cfg)

    async def _rag_circuit_enabled(self, rf: RAGFilter) -> bool:
        from spark.core.production_profile import ProductionProfile
        from spark.services.factory_config_service import factory_config_service

        if rf.factory_id:
            async with AsyncSessionLocal() as session:
                factory_cfg = await factory_config_service.resolve(session, rf.factory_id)
            return ProductionProfile.for_factory(factory_cfg).rag_circuit_enabled
        return ProductionProfile.from_settings().rag_circuit_enabled

    async def retrieve_lexical(
        self,
        query: str,
        rf: RAGFilter,
        top_k: int,
        allowed_doc_ids: list[str] | None = None,
    ) -> tuple[list[RetrievedDoc], bool]:
        """Return lexical hits and whether the leg failed."""
        engine = await self.resolve_lexical_engine(rf)
        lexical_query = expand_lexical_variants(query)
        try:
            from spark.retrieval.lexical import retrieve_lexical_candidates

            hits = await retrieve_lexical_candidates(
                lexical_query,
                rf,
                top_k,
                allowed_doc_ids=allowed_doc_ids,
                engine=engine,
            )
            return hits, False
        except Exception as exc:
            log.error(
                "rag_postgres_lexical_failed",
                error=str(exc)[:500],
                engine=engine,
                factory_id=rf.factory_id,
                exc_info=True,
            )
            rag_lexical_degraded_total.labels(engine=engine, reason=type(exc).__name__).inc()
            return [], True

    async def _retrieve_multi_hop(
        self,
        query: str,
        rf: RAGFilter,
        top_k: int,
        allowed_doc_ids: list[str] | None = None,
        *,
        session_id: str | None = None,
        deadline: RequestDeadline | None = None,
    ) -> tuple[list[RetrievedDoc], RetrievalReport] | None:
        """Attempt multi-hop decomposition; return None if query is atomic."""
        from spark.retrieval.preprocess.decompose import decompose_query

        decomposed = await decompose_query(query)
        if decomposed is None:
            return None

        all_docs: list[list[RetrievedDoc]] = []
        for sub_q in decomposed.sub_queries:
            sub_docs, _ = await self.retrieve(
                sub_q, rf, top_k,
                allowed_doc_ids=allowed_doc_ids,
                session_id=session_id,
                deadline=deadline,
                _skip_intent_boost=True,
                _skip_decomposition=True,
            )
            all_docs.append(sub_docs)

        merged = fuse_candidates(
            all_docs,
            method="rrf",
            weights=[1.0] * len(all_docs),
            rrf_k=60,
            identity_fn=retrieval_identity,
        )[:top_k * settings.rag_retrieve_multiplier]

        report = build_retrieval_report(
            intent="multi_hop",
            fusion_method="multi_hop_rrf",
            vector_count=sum(len(d) for d in all_docs),
            lexical_count=0,
            failed_collections=[],
        )
        self.last_report = report
        return merged, report

    async def retrieve(
        self,
        query: str,
        rf: RAGFilter,
        top_k: int,
        allowed_doc_ids: list[str] | None = None,
        *,
        session_id: str | None = None,
        intent_plan: IntentPlan | None = None,
        follow_up: bool = False,
        last_retrieved_chunk_ids: list[str] | None = None,
        deadline: RequestDeadline | None = None,
        evidence_age_turns: int | None = None,
        _skip_intent_boost: bool = False,
        _skip_decomposition: bool = False,
    ) -> tuple[list[RetrievedDoc], RetrievalReport]:
        from spark.observability.otel_tracing import record_span_event, start_span

        retrieve_start = time.perf_counter()
        if deadline is None:
            deadline = RequestDeadline.from_settings(started_at=retrieve_start)
        if deadline.expired():
            empty = build_retrieval_report(
                intent="general",
                fusion_method="weighted_rrf",
                vector_count=0,
                lexical_count=0,
                failed_collections=[],
            )
            self.last_report = empty
            return [], empty
        if allowed_doc_ids is not None and not allowed_doc_ids:
            empty = build_retrieval_report(
                intent="general",
                fusion_method="weighted_rrf",
                vector_count=0,
                lexical_count=0,
                failed_collections=[],
            )
            self.last_report = empty
            return [], empty

        # Decomposition also runs in the chat path (which always supplies an
        # intent_plan). decompose_query() short-circuits on the fast
        # should_attempt_decomposition() heuristic, so atomic questions pay only
        # a regex check — but genuine multi-topic questions (machine-vs-machine
        # comparisons, or a machinery + welfare/policy question) now retrieve
        # evidence for every topic instead of only the dominant one.
        if not follow_up and not _skip_decomposition:
            multi_hop = await self._retrieve_multi_hop(
                query, rf, top_k,
                allowed_doc_ids=allowed_doc_ids,
                session_id=session_id,
                deadline=deadline,
            )
            if multi_hop is not None:
                return multi_hop

        plan = intent_plan or self.intent_router.route(query)
        self.last_intent_plan = plan
        scoped_rf = apply_intent_to_filter(plan, rf)
        fusion_cfg = await self.resolve_fusion_config(scoped_rf)
        fusion_method: FusionMethod = fusion_cfg.method
        weights = resolve_hybrid_weights(
            plan.dense_weight,
            plan.lexical_weight,
            fusion_cfg,
        )

        vector_start = time.perf_counter()
        if deadline.expired():
            report = build_retrieval_report(
                intent=plan.intent.value,
                fusion_method=fusion_method,
                vector_count=0,
                lexical_count=0,
                failed_collections=[],
            )
            self.last_report = report
            return [], report

        # Multi-query dense retrieval: a Thai question whose answer lives in an
        # English-only manual can miss on the raw-query embedding alone. When the
        # glossary adds English variants, run a second dense leg with the
        # expanded query CONCURRENTLY and fuse both lists — no extra latency,
        # no LLM call.
        expanded_query = expand_lexical_variants(query)
        run_expanded_leg = (
            bool(getattr(settings, "rag_multi_query_expansion", True))
            and expanded_query != query
        )
        with start_span(
            "rag.retrieve.vector",
            intent=plan.intent.value,
            factory_id=scoped_rf.factory_id or "",
            top_k=top_k,
        ) as vec_span:
            import asyncio

            async def _dense_leg(dense_query: str):
                return await search_qdrant_hybrid(
                    query=dense_query,
                    rf=scoped_rf,
                    top_k=top_k,
                    embedder=self.embedder,
                    get_client=get_async_qdrant_client,
                    ensure_collection=ensure_collection,
                    allowed_doc_ids=allowed_doc_ids,
                )

            expanded_hits: list[RetrievedDoc] = []
            if run_expanded_leg:
                vector_result, expanded_result = await asyncio.gather(
                    _dense_leg(query),
                    _dense_leg(expanded_query),
                    return_exceptions=False,
                )
                if not getattr(expanded_result, "embed_failed", False):
                    expanded_hits = expanded_result.hits
                    log.info(
                        "rag_multi_query_expansion",
                        expanded_query=expanded_query[:160],
                        expanded_candidates=len(expanded_hits),
                    )
            else:
                vector_result = await _dense_leg(query)
            record_span_event(vec_span, "vector_complete", candidates=len(vector_result.hits), embed_failed=vector_result.embed_failed)
        raw_hits = vector_result.hits
        if vector_result.embed_failed:
            rag_embed_error_total.inc()
            circuit_enabled = await self._rag_circuit_enabled(scoped_rf)
            from spark.retrieval.safety.circuit_breaker import record_rag_outcome_async

            await record_rag_outcome_async(
                "embed_error",
                enabled=circuit_enabled,
                factory_id=scoped_rf.factory_id,
            )
        log.info(
            "rag_retrieval_path",
            source="vector",
            candidates=len(raw_hits),
            returned=len(raw_hits),
            latency_ms=round((time.perf_counter() - vector_start) * 1000, 2),
            intent=plan.intent.value,
            sparse_encoder_id=vector_result.sparse_encoder_id,
        )
        rag_retrieval_leg_seconds.labels("vector").observe(time.perf_counter() - vector_start)

        lexical_start = time.perf_counter()
        lexical_budget_ms = int(getattr(settings, "rag_lexical_budget_ms", 5_000) or 5_000)
        if deadline.remaining_ms() - _MIN_LLM_BUDGET_MS < lexical_budget_ms:
            log.info(
                "rag_lexical_skipped_deadline",
                remaining_ms=deadline.remaining_ms(),
                lexical_budget_ms=lexical_budget_ms,
            )
            lexical_hits, lexical_failed = [], False
        else:
            with start_span("rag.retrieve.lexical", factory_id=scoped_rf.factory_id or "", top_k=top_k) as lex_span:
                lexical_hits, lexical_failed = await self.retrieve_lexical(
                    query, scoped_rf, top_k, allowed_doc_ids=allowed_doc_ids
                )
                record_span_event(lex_span, "lexical_complete", candidates=len(lexical_hits), failed=lexical_failed)
        rag_retrieval_leg_seconds.labels("lexical").observe(time.perf_counter() - lexical_start)

        exact_start = time.perf_counter()
        exact_hits: list[RetrievedDoc] = []
        if not deadline.expired():
            with start_span("rag.retrieve.exact", factory_id=scoped_rf.factory_id or "", top_k=top_k) as exact_span:
                try:
                    exact_hits = await retrieve_exact_evidence_candidates(
                        query,
                        scoped_rf,
                        top_k,
                        plan=plan,
                        allowed_doc_ids=allowed_doc_ids,
                    )
                    if plan.intent == QueryIntent.IO_MAPPING:
                        for tag in extract_plc_tags(query)[:3]:
                            exact_hits.extend(
                                await search_qdrant_exact_tag(
                                    tag,
                                    scoped_rf,
                                    top_k,
                                    get_client=get_async_qdrant_client,
                                    allowed_doc_ids=allowed_doc_ids,
                                )
                            )
                    record_span_event(exact_span, "exact_complete", candidates=len(exact_hits))
                except Exception as exc:  # noqa: BLE001
                    log.warning("rag_exact_evidence_failed", error=str(exc)[:300])
        rag_retrieval_leg_seconds.labels("exact").observe(time.perf_counter() - exact_start)

        report = build_retrieval_report(
            intent=plan.intent.value,
            fusion_method=fusion_method,
            vector_count=len(raw_hits) + len(expanded_hits),
            lexical_count=len(lexical_hits),
            failed_collections=vector_result.failed_collections,
            embed_failed=vector_result.embed_failed,
            lexical_failed=lexical_failed,
            sparse_encoder_id=vector_result.sparse_encoder_id,
        )
        self.last_report = report

        if not raw_hits and not expanded_hits and not lexical_hits and not exact_hits:
            return [], report

        fusion_start = time.perf_counter()
        candidate_lists: list[list[RetrievedDoc]] = []
        fusion_weights: list[float] = []
        if raw_hits:
            candidate_lists.append(raw_hits)
            fusion_weights.append(float(weights[0]))
        if expanded_hits:
            # Slightly below the raw-query leg so the user's own wording wins ties.
            candidate_lists.append(expanded_hits)
            fusion_weights.append(float(weights[0]) * 0.8)
        if lexical_hits:
            candidate_lists.append(lexical_hits)
            fusion_weights.append(float(weights[1]))
        if exact_hits:
            candidate_lists.append(exact_hits)
            fusion_weights.append(max(0.5, sum(float(w) for w in weights)))
        with start_span("rag.retrieve.fusion", method=fusion_method, vector_count=len(raw_hits), lexical_count=len(lexical_hits)):
            merged_hits = fuse_candidates(
                candidate_lists,
                method=fusion_method,
                weights=fusion_weights,
                rrf_k=fusion_cfg.rrf_k,
                identity_fn=retrieval_identity,
            )
        if not _skip_intent_boost:
            merged_hits = apply_intent_boosts(plan, merged_hits)
        from spark.retrieval.preprocess.follow_up_boost import boost_follow_up_chunks
        from spark.retrieval.fusion_weights import sparse_leg_snapshot

        sparse_meta = sparse_leg_snapshot(sparse_encoder_id=vector_result.sparse_encoder_id)

        merged_hits = boost_follow_up_chunks(
            merged_hits,
            chunk_ids=last_retrieved_chunk_ids,
            follow_up=follow_up,
            question=query,
            evidence_age_turns=evidence_age_turns,
        )
        merged_hits = merged_hits[: max(top_k * settings.rag_retrieve_multiplier, CANDIDATE_POOL_LIMIT)]
        rag_retrieval_leg_seconds.labels("fusion").observe(time.perf_counter() - fusion_start)

        log_retrieval_features(
            query_id=session_id,
            candidates=merged_hits,
            plan=plan,
            weight_version=plan.weight_version,
            factory_id=scoped_rf.factory_id,
            vector_count=len(raw_hits),
            lexical_count=len(lexical_hits),
            sparse_leg_weight=float(sparse_meta.get("sparse_leg_weight") or 0.0),
            sparse_encoder_id=vector_result.sparse_encoder_id,
        )

        log.debug(
            "rag_fusion_top_candidates",
            fusion_method=fusion_method,
            intent=plan.intent.value,
            candidates=[
                {
                    "chunk_id": doc.payload.get("chunk_id"),
                    "fusion_score": round(float(doc.fusion_score or doc.score), 4),
                }
                for doc in merged_hits[:5]
            ],
        )

        reranked = merged_hits
        rerank_top_k = top_k
        if exact_hits:
            if plan.intent == QueryIntent.IO_MAPPING:
                rerank_top_k = max(top_k, min(len(merged_hits), 40))
            elif plan.intent == QueryIntent.DRAWING:
                rerank_top_k = max(top_k, min(len(merged_hits), 16))
            else:
                rerank_top_k = max(top_k, min(len(merged_hits), 12))
        if self._apply_rerank is not None and deadline.remaining_ms() >= _MIN_LLM_BUDGET_MS:
            with start_span("rag.retrieve.rerank", candidates=len(merged_hits), top_k=top_k):
                reranked = await self._apply_rerank(
                    query,
                    merged_hits,
                    rerank_top_k,
                    session_id=session_id,
                    intent_plan=plan,
                    deadline=deadline,
                )
        elif self._apply_rerank is not None and deadline.remaining_ms() < _MIN_LLM_BUDGET_MS:
            reranked = merged_hits[:rerank_top_k]

        if reranked:
            hydrate_start = time.perf_counter()
            async with AsyncSessionLocal() as session:
                await hydrate_parent_content_from_pg(session, reranked)
            rag_retrieval_leg_seconds.labels("hydrate").observe(time.perf_counter() - hydrate_start)

        log.info(
            "rag_retrieval_complete",
            fusion_method=fusion_method,
            intent=plan.intent.value,
            sources=_retrieval_sources_from_docs(reranked),
            vector_candidates=len(raw_hits),
            lexical_candidates=len(lexical_hits),
            returned=len(reranked),
            degraded=report.degraded,
            sparse_encoder_id=report.sparse_encoder_id,
            lexical_latency_ms=round((time.perf_counter() - lexical_start) * 1000, 2),
            total_latency_ms=round((time.perf_counter() - retrieve_start) * 1000, 2),
        )
        return reranked, report
