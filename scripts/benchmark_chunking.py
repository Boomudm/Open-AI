#!/usr/bin/env python3
"""Benchmark chunk sizes for MC-001 manual retrieval quality (issue #46).

Compares chunk_size 256 / 512 / 1024 (with proportional overlap) using a fixed
question set. Uses embedding cosine similarity when Ollama is up, else lexical MRR.

Usage:
  python scripts/benchmark_chunking.py [--manual-path PATH] [--output docs/chunking_benchmark.md]
"""
from __future__ import annotations

import argparse
import asyncio
import math
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spark.core.config import settings
from spark.core.logging import configure_logging, get_logger
from spark.ingestion.chunk.registry import chunk_text
from spark.services.reranker import lexical_overlap_score

configure_logging()
log = get_logger("benchmark_chunking")

IMPROVEMENT_THRESHOLD = 0.05  # 5% MRR@6 gain to change production profile
CURRENT_PROFILE = (1200, 200)

BENCHMARK_PROFILES: list[tuple[str, int, int]] = [
    ("256", 256, 64),
    ("512", 512, 128),
    ("1024", 1024, 200),
    ("current_1200", 1200, 200),
]

GOLDEN_QUESTIONS: list[str] = [
    "Servo Motor MC-001 ร้อนผิดปกติ ต้องทำอะไร",
    "MC-001 cooling fan temperature limit",
    "MC-001 bearing maintenance interval",
    "Servo driver MR-J5 warning overheating",
    "MC-001 encoder calibration procedure",
]

SAMPLE_MANUAL_TEXT = """
Servo Motor Line A MC-001 Operation Manual — Mitsubishi MR-J5

Chapter 3 — Cooling and Temperature
WARNING: High temperature may damage the servo driver. Check cooling fan if temperature exceeds 80°C.
If overheating persists, stop the motor immediately and inspect the cooling fan and heat sink.
Normal operating temperature range is 0°C to 55°C ambient.

Chapter 4 — Bearing Maintenance
Replace bearing MC001-C03 every 5000 operating hours. Use torque wrench 10 mm socket.
Inspect bearing for noise and vibration during weekly checks.

Chapter 5 — Encoder
Encoder MC001-C02 calibration: connect diagnostic cable, run auto-alignment from panel menu.
Servo driver fault code E001 indicates encoder communication error.

Chapter 6 — Hydraulic Press MC-002 (shared plant manual excerpt)
Hydraulic Press B uses ISO VG 46 oil. Check oil temperature before each shift.
""".strip()


@dataclass
class ProfileScore:
    name: str
    chunk_size: int
    chunk_overlap: int
    chunk_count: int
    mrr_at_6: float
    hit_at_6: float
    mode: str


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _rank_chunks_lexical(question: str, chunks: list[str], top_k: int = 6) -> list[int]:
    scored = [(i, lexical_overlap_score(question, c)) for i, c in enumerate(chunks)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [i for i, _ in scored[:top_k]]


def _rank_chunks_embed(question: str, chunks: list[str], q_vec: list[float], chunk_vecs: list[list[float]], top_k: int = 6) -> list[int]:
    scored = [(i, _cosine(q_vec, chunk_vecs[i])) for i in range(len(chunks))]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [i for i, _ in scored[:top_k]]


def _chunk_relevant(chunk: str) -> bool:
    keys = ("temperature", "cooling", "bearing", "encoder", "80", "overheat", "mr-j5", "5000")
    lower = chunk.lower()
    return any(k in lower for k in keys)


def _mrr_and_hit(ranked_indices: list[int], chunks: list[str], top_k: int = 6) -> tuple[float, float]:
    relevant = {i for i, c in enumerate(chunks) if _chunk_relevant(c)}
    if not relevant:
        return 0.0, 0.0
    mrr = 0.0
    hit = 0.0
    for rank, idx in enumerate(ranked_indices[:top_k], start=1):
        if idx in relevant:
            mrr = max(mrr, 1.0 / rank)
            hit = 1.0
            break
    return mrr, hit


def score_profile(
    name: str,
    chunk_size: int,
    chunk_overlap: int,
    text: str,
    *,
    embed_mode: bool,
    embedder: object | None,
    strategy: str | None = None,
    offline_only: bool = False,
    semantic_breakpoint_threshold: float | None = None,
) -> ProfileScore:
    if strategy and semantic_breakpoint_threshold is not None:
        chunks = chunk_text(
            text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            strategy=strategy,
            offline_only=offline_only,
            semantic_breakpoint_threshold=semantic_breakpoint_threshold,
        )
    elif strategy:
        from spark.ingestion.chunk.strategies import get_chunking_strategy

        chunks = get_chunking_strategy(strategy).split(
            text, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
    else:
        chunks = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        return ProfileScore(name, chunk_size, chunk_overlap, 0, 0.0, 0.0, "none")

    mrrs: list[float] = []
    hits: list[float] = []
    mode = "lexical"

    async def _embed_score() -> None:
        nonlocal mode
        mode = "embedding"
        assert embedder is not None
        chunk_vecs = await embedder.embed_documents(chunks)
        for q in GOLDEN_QUESTIONS:
            q_vec = await embedder.embed_query(q)
            ranked = _rank_chunks_embed(q, chunks, q_vec, chunk_vecs)
            mrr, hit = _mrr_and_hit(ranked, chunks)
            mrrs.append(mrr)
            hits.append(hit)

    if embed_mode and embedder is not None:
        asyncio.run(_embed_score())
    else:
        for q in GOLDEN_QUESTIONS:
            ranked = _rank_chunks_lexical(q, chunks)
            mrr, hit = _mrr_and_hit(ranked, chunks)
            mrrs.append(mrr)
            hits.append(hit)

    return ProfileScore(
        name=name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        chunk_count=len(chunks),
        mrr_at_6=sum(mrrs) / len(mrrs),
        hit_at_6=sum(hits) / len(hits),
        mode=mode,
    )


def _load_manual_text(path: Path | None) -> str:
    if path and path.exists():
        if path.suffix.lower() == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            parts = []
            for page in reader.pages:
                parts.append(page.extract_text() or "")
            text = "\n".join(parts).strip()
            if text:
                return text
        return path.read_text(encoding="utf-8", errors="replace")
    return SAMPLE_MANUAL_TEXT


def _pick_winner(scores: list[ProfileScore]) -> ProfileScore:
    candidates = [s for s in scores if s.name != "current_1200"]
    return max(candidates, key=lambda s: s.mrr_at_6)


def _render_markdown(scores: list[ProfileScore], text_source: str, embed_mode: bool) -> str:
    winner = _pick_winner(scores)
    current = next(s for s in scores if s.name == "current_1200")
    improve = (winner.mrr_at_6 - current.mrr_at_6) / max(current.mrr_at_6, 1e-9)
    recommend_change = improve >= IMPROVEMENT_THRESHOLD and winner.name != "current_1200"

    lines = [
        "# Chunking benchmark — MC-001 manual",
        "",
        "Generated by `scripts/benchmark_chunking.py` (issue #46).",
        "",
        f"- Text source: `{text_source}`",
        f"- Scoring mode: **{'embedding cosine' if embed_mode else 'lexical overlap'}**",
        f"- Questions: {len(GOLDEN_QUESTIONS)} fixed golden queries",
        "- Metric: mean MRR@6 and Hit@6 over question set",
        f"- Improvement threshold: {IMPROVEMENT_THRESHOLD:.0%}",
        "",
        "## Results",
        "",
        "| Profile | chunk_size | overlap | chunks | MRR@6 | Hit@6 |",
        "|---------|------------|---------|--------|-------|-------|",
    ]
    for s in scores:
        lines.append(
            f"| {s.name} | {s.chunk_size} | {s.chunk_overlap} | {s.chunk_count} "
            f"| {s.mrr_at_6:.3f} | {s.hit_at_6:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            f"- **Winner:** `{winner.name}` (MRR@6={winner.mrr_at_6:.3f})",
            f"- **Current production** (`long_form_th` 1200/200): MRR@6={current.mrr_at_6:.3f}",
            f"- **Delta:** {improve:+.1%}",
        ]
    )
    if recommend_change:
        lines.append(
            f"- **Action:** update `configs/chunking_profiles.yaml` profile `long_form_th` "
            f"to chunk_size={winner.chunk_size}, chunk_overlap={winner.chunk_overlap}"
        )
    else:
        lines.append("- **Action:** keep current `long_form_th` (1200/200) — no gain above threshold")

    lines.extend(["", "## Question set", ""])
    for q in GOLDEN_QUESTIONS:
        lines.append(f"- {q}")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark chunk sizes for retrieval")
    parser.add_argument("--manual-path", type=Path, help="PDF or text manual (default: built-in sample)")
    parser.add_argument("--output", type=Path, default=Path("docs/chunking_benchmark.md"))
    parser.add_argument(
        "--semantic",
        action="store_true",
        help="Offline-only: run semantic_1200 embedding breakpoint gate vs current_1200",
    )
    parser.add_argument(
        "--offline-only",
        action="store_true",
        help="Acknowledge offline/benchmark-only semantic embedding chunking (required with --semantic)",
    )
    args = parser.parse_args()

    text = _load_manual_text(args.manual_path)
    source_label = str(args.manual_path) if args.manual_path else "built-in sample (MC-001-like)"

    embedder = None
    embed_mode = False
    try:
        import httpx

        httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2).raise_for_status()
        from spark.ingestion.embedder import Embedder

        embedder = Embedder.get()
        embed_mode = True
    except Exception:
        log.warning("ollama_unavailable_lexical_only")

    scores: list[ProfileScore] = []
    for name, size, overlap in BENCHMARK_PROFILES:
        s = score_profile(name, size, overlap, text, embed_mode=embed_mode, embedder=embedder)
        scores.append(s)
        print(f"{s.name:12} chunks={s.chunk_count:4d}  MRR@6={s.mrr_at_6:.3f}  Hit@6={s.hit_at_6:.3f}  ({s.mode})")

    if args.semantic:
        if not args.offline_only:
            parser.error("--semantic requires --offline-only (embedding chunking is not on ingest hot path)")
        semantic = score_profile(
            "semantic_1200",
            1200,
            200,
            text,
            embed_mode=embed_mode,
            embedder=embedder,
            strategy="semantic",
            offline_only=True,
            semantic_breakpoint_threshold=0.5,
        )
        scores.append(semantic)
        print(
            f"{semantic.name:12} chunks={semantic.chunk_count:4d}  "
            f"MRR@6={semantic.mrr_at_6:.3f}  Hit@6={semantic.hit_at_6:.3f}  ({semantic.mode})"
        )
        current = next(s for s in scores if s.name == "current_1200")
        delta = (semantic.mrr_at_6 - current.mrr_at_6) / max(current.mrr_at_6, 1e-9)
        print(f"\nSemantic gate: semantic_1200 vs current_1200 delta={delta:+.1%}")
        if delta < IMPROVEMENT_THRESHOLD:
            print(
                f"FAIL: semantic_1200 must beat current_1200 by >= {IMPROVEMENT_THRESHOLD:.0%}"
            )
            raise SystemExit(1)
        print(f"PASS: semantic_1200 meets {IMPROVEMENT_THRESHOLD:.0%} improvement threshold")

    md = _render_markdown(scores, source_label, embed_mode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(md, encoding="utf-8")
    print(f"\nWrote {args.output}")

    winner = _pick_winner(scores)
    current = next(s for s in scores if s.name == "current_1200")
    if (winner.mrr_at_6 - current.mrr_at_6) / max(current.mrr_at_6, 1e-9) >= IMPROVEMENT_THRESHOLD:
        print(f"Recommend: switch long_form_th to {winner.chunk_size}/{winner.chunk_overlap}")


if __name__ == "__main__":
    main()
