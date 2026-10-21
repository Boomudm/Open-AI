"""Import all model modules so SQLAlchemy registers their tables with `Base.metadata`.

`alembic autogenerate` and `Base.metadata.create_all` rely on these imports.
"""

from spark.db.models import (  # noqa: F401
    api_keys,
    chat,
    data_sources,
    docs,
    feedback,
    ingestion,
    ingestion_events,
    job_positions,
    org,
    qa_cache,
    rag_audit,
    worm_audit,
)

__all__ = [
    "api_keys",
    "chat",
    "data_sources",
    "docs",
    "feedback",
    "ingestion",
    "ingestion_events",
    "job_positions",
    "org",
    "qa_cache",
    "rag_audit",
    "worm_audit",
]
