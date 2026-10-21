"""Golden-set leakage detection for the held-out evaluation protocol.

A held-out set is only meaningful if the development/tuning set does not contain the
same (or near-duplicate) questions — otherwise reported "held-out" scores are inflated
by memorization/overfitting, exactly the failure mode this pipeline had.

This module provides deterministic, dependency-free primitives to:
  * normalize questions (case, punctuation, whitespace; Thai-aware),
  * detect exact overlaps via fingerprint,
  * detect near-duplicates via character-shingle Jaccard similarity,
  * extract questions from an evaluation config (flat cases + multi-turn chains).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

# Keep word chars and the Thai block; drop everything else (punctuation, symbols).
_NON_TOKEN = re.compile(r"[^\w\u0E00-\u0E7F]+")
_WS = re.compile(r"\s+")


def normalize_question(question: str) -> str:
    text = (question or "").strip().lower()
    text = _NON_TOKEN.sub(" ", text)
    return _WS.sub(" ", text).strip()


def question_fingerprint(question: str) -> str:
    return hashlib.sha1(normalize_question(question).encode("utf-8")).hexdigest()


def char_shingles(question: str, n: int = 4) -> frozenset[str]:
    """Character n-grams over the de-spaced normalized text.

    Character shingles are robust to Thai's lack of word boundaries and to small
    edits/word-order changes that token sets miss.
    """
    text = normalize_question(question).replace(" ", "")
    if not text:
        return frozenset()
    if len(text) <= n:
        return frozenset({text})
    return frozenset(text[i : i + n] for i in range(len(text) - n + 1))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True)
class LeakagePair:
    dev_question: str
    holdout_question: str
    similarity: float
    kind: str  # "exact" | "near"


@dataclass
class LeakageReport:
    exact: list[LeakagePair] = field(default_factory=list)
    near: list[LeakagePair] = field(default_factory=list)

    @property
    def leaked(self) -> bool:
        return bool(self.exact or self.near)

    @property
    def total(self) -> int:
        return len(self.exact) + len(self.near)


def find_leakage(
    dev_questions: Iterable[str],
    holdout_questions: Iterable[str],
    *,
    near_dup_threshold: float = 0.7,
    shingle_size: int = 4,
) -> LeakageReport:
    """Return exact and near-duplicate overlaps of held-out questions with dev questions."""
    dev_list = [q for q in dev_questions if (q or "").strip()]
    dev_fps = {question_fingerprint(q): q for q in dev_list}
    dev_shingles = [(q, char_shingles(q, shingle_size)) for q in dev_list]

    report = LeakageReport()
    for hq in holdout_questions:
        if not (hq or "").strip():
            continue
        fp = question_fingerprint(hq)
        if fp in dev_fps:
            report.exact.append(LeakagePair(dev_fps[fp], hq, 1.0, "exact"))
            continue
        hshingles = char_shingles(hq, shingle_size)
        best: LeakagePair | None = None
        for dq, dshingles in dev_shingles:
            sim = jaccard(dshingles, hshingles)
            if sim >= near_dup_threshold and (best is None or sim > best.similarity):
                best = LeakagePair(dq, hq, round(sim, 4), "near")
        if best is not None:
            report.near.append(best)
    return report


def extract_questions(config: dict[str, Any]) -> list[str]:
    """Pull every natural-language question from an evaluation config (cases + chains)."""
    questions: list[str] = []
    for case in config.get("cases") or []:
        if not isinstance(case, dict):
            continue
        q = case.get("question")
        if isinstance(q, str) and q.strip():
            questions.append(q)
        for turn in case.get("turns") or []:
            if isinstance(turn, dict):
                tq = turn.get("question")
                if isinstance(tq, str) and tq.strip():
                    questions.append(tq)
    return questions
