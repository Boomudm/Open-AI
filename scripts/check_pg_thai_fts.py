#!/usr/bin/env python3
"""Probe PostgreSQL FTS configs for Phase 6 lexical engine."""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, text

from spark.core.config import settings


def main() -> int:
    engine = create_engine(settings.database_url_sync)
    with engine.connect() as conn:
        thai_cfg = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'thai')")
        ).scalar()
        simple_cfg = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'simple')")
        ).scalar()
        trgm = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm')")
        ).scalar()
    print(f"pg_ts_config thai={bool(thai_cfg)} simple={bool(simple_cfg)} pg_trgm={bool(trgm)}")
    if not simple_cfg or not trgm:
        return 1
    if not thai_cfg:
        print("note: using PyThaiNLP tokenized simple FTS fallback (content_tsv_th)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
