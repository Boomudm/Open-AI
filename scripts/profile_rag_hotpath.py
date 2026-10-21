#!/usr/bin/env python3
"""In-process RAG hot-path profiler — the real replacement for the fake soaks.

Runs the full RAGService.query pipeline N times and reports, per run: total
latency, answer_path, and every LLM round-trip (wrapped at ChatOpenAI /
ChatOllama.ainvoke) with its duration and prompt size. Structured pipeline logs
(rag_retrieval_path, rag_rerank_complete, ...) interleave on stdout, so one run
shows exactly where the seconds go.

Must run INSIDE the api container — it imports the app and talks to the live
Qdrant/Postgres/LLM the app is configured for, and it needs no HTTP auth:

    docker cp scripts/profile_rag_hotpath.py spark_api:/tmp/
    docker exec spark_api python /tmp/profile_rag_hotpath.py \
        --runs 6 --factory F-05 \
        --question "อุณหภูมิของเซอร์โวมอเตอร์สูงเกินไปต้องทำอย่างไร"

Findings from this profiler (2026-07-15, Jetson + KKU gateway): warm retrieval
~0.4s, rerank 1.6s (fp16 sidecar), LLM generation 5-32s = 44-82% of wall; the
gateway also non-deterministically stalls or refuses — see rag_generation_retry
settings in core/config.py.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import time
import traceback

CALLS: list[tuple[str, float, int]] = []
RUN_T0 = 0.0


def _patch_llm_clients() -> None:
    """Wrap every chat-model ainvoke so each LLM round-trip is visible."""
    from langchain_openai import ChatOpenAI

    classes = [ChatOpenAI]
    try:
        from langchain_ollama import ChatOllama

        classes.append(ChatOllama)
    except ImportError:
        pass

    for cls in classes:
        orig = cls.ainvoke
        if getattr(orig, "_prof", False):
            continue

        async def ainvoke(self, input, config=None, _orig=orig, **kw):
            stack = [f.name for f in traceback.extract_stack()[-14:-1]]
            frames = [s for s in stack if s not in ("ainvoke", "<module>", "main", "wrapper")]
            label = frames[-1] if frames else "?"
            prompt_chars = len(str(input))
            started = time.perf_counter()
            try:
                return await _orig(self, input, config, **kw)
            finally:
                elapsed_ms = (time.perf_counter() - started) * 1000
                CALLS.append((label, elapsed_ms, prompt_chars))
                print(
                    f"    LLM[{label}] {elapsed_ms:.0f}ms prompt={prompt_chars}c "
                    f"@t+{time.perf_counter() - RUN_T0:.1f}s",
                    flush=True,
                )

        ainvoke._prof = True  # type: ignore[attr-defined]
        cls.ainvoke = ainvoke


async def profile(question: str, factory_id: str | None, runs: int, top_k: int) -> None:
    global RUN_T0
    _patch_llm_clients()
    from spark.retrieval.models import RAGFilter
    from spark.retrieval.service import RAGService

    svc = RAGService()
    rf = RAGFilter(factory_id=factory_id) if factory_id else RAGFilter()

    paths: collections.Counter[str] = collections.Counter()
    totals: list[float] = []
    for i in range(runs):
        CALLS.clear()
        RUN_T0 = time.perf_counter()
        print(f"\n===== RUN {i} =====", flush=True)
        started = time.perf_counter()
        try:
            res = await svc.query(question, rf, top_k=top_k)
            path = getattr(res, "answer_path", "?")
        except Exception as exc:
            path = f"EXC:{type(exc).__name__}"
            traceback.print_exc()
        total = time.perf_counter() - started
        paths[path] += 1
        totals.append(total)
        llm_ms = sum(c[1] for c in CALLS)
        print(
            f"  TOTAL {total:.1f}s path={path} llm_calls={len(CALLS)} "
            f"llm={llm_ms / 1000:.1f}s ({llm_ms / 10 / max(total, 0.01):.0f}% of wall)",
            flush=True,
        )

    print("\n===== SUMMARY =====", flush=True)
    for path, count in paths.most_common():
        print(f"  {path:24s} {count}/{runs}", flush=True)
    ordered = sorted(totals)
    print(
        f"  latency med={ordered[len(ordered) // 2]:.1f}s "
        f"min={ordered[0]:.1f}s max={ordered[-1]:.1f}s",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--question",
        default="อุณหภูมิของเซอร์โวมอเตอร์สูงเกินไปต้องทำอย่างไร",
    )
    parser.add_argument("--factory", default=None, help="factory_id filter (e.g. F-05)")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=6)
    args = parser.parse_args()
    asyncio.run(profile(args.question, args.factory, args.runs, args.top_k))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
