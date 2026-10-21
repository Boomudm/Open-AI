#!/usr/bin/env python3
"""Audit a held-out evaluation set for golden-set leakage against the dev/tuning set.

A held-out set must contain no exact or near-duplicate questions from the development
set, otherwise its scores are contaminated by overfitting. Run this in CI before
trusting any held-out number.

Usage:
    python scripts/eval_leakage_audit.py \
        --dev configs/evaluation_baseline.yaml \
        --holdout configs/evaluation_heldout.yaml \
        --threshold 0.8
Exit code is non-zero when leakage is detected.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spark.eval.leakage import extract_questions, find_leakage  # noqa: E402


def _load_questions(path: Path) -> list[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return extract_questions(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Held-out leakage audit")
    parser.add_argument("--dev", type=Path, default=Path("configs/evaluation_baseline.yaml"))
    parser.add_argument("--holdout", type=Path, default=Path("configs/evaluation_heldout.yaml"))
    parser.add_argument("--threshold", type=float, default=0.7, help="near-duplicate Jaccard cutoff")
    parser.add_argument("--no-fail", action="store_true", help="report only, always exit 0")
    args = parser.parse_args()

    dev_questions = _load_questions(args.dev)
    holdout_questions = _load_questions(args.holdout)

    report = find_leakage(
        dev_questions, holdout_questions, near_dup_threshold=args.threshold
    )

    print("=" * 72)
    print("Held-out leakage audit")
    print(f"  dev set:     {args.dev} ({len(dev_questions)} questions)")
    print(f"  held-out:    {args.holdout} ({len(holdout_questions)} questions)")
    print(f"  threshold:   {args.threshold}")
    print("-" * 72)
    if not report.leaked:
        print("CLEAN: no exact or near-duplicate overlap detected.")
        print("=" * 72)
        return

    for pair in report.exact:
        print(f"[EXACT] held-out leaks dev question:\n  dev:     {pair.dev_question}\n  holdout: {pair.holdout_question}")
    for pair in report.near:
        print(
            f"[NEAR {pair.similarity:.2f}] held-out near-duplicate of dev question:\n"
            f"  dev:     {pair.dev_question}\n  holdout: {pair.holdout_question}"
        )
    print("-" * 72)
    print(f"LEAKAGE DETECTED: {report.total} overlapping question(s).")
    print("=" * 72)
    if not args.no_fail:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
