"""BGE-M3 tokenizer-index sparse vectors (real vocab IDs, not hash buckets)."""

from __future__ import annotations

import math
from collections import Counter
from functools import lru_cache

from qdrant_client.models import SparseVector


def _import_auto_tokenizer():
    """Import AutoTokenizer, tolerating transformers' concurrent-import race.

    ``transformers`` builds its top-level namespace lazily, so a thread importing
    it while another thread is midway through the same import can observe a
    partially initialised module and raise ImportError ("cannot import name
    'AutoTokenizer'"). Workers hit this on the first sparse encode after a
    restart, which surfaced as a spurious ``service_unavailable`` on a user's
    first query. The loser of the race only has to wait for the winner to finish,
    so a short bounded retry resolves it; the import is memoised by sys.modules
    thereafter, making this a startup-only cost.
    """
    import time as _time

    last_exc: Exception | None = None
    for attempt in range(5):
        try:
            from transformers import AutoTokenizer

            return AutoTokenizer
        except ImportError as exc:  # partially initialised module — let it settle
            last_exc = exc
            _time.sleep(0.25 * (attempt + 1))
    raise RuntimeError(
        f"transformers.AutoTokenizer unavailable after retries: {last_exc}"
    ) from last_exc


@lru_cache(maxsize=1)
def _load_tokenizer():
    AutoTokenizer = _import_auto_tokenizer()

    from spark.core.llm_profile import sparse_tokenizer_model

    model_name = sparse_tokenizer_model()
    try:
        # Same fix as the embedder/reranker: from_pretrained() without
        # local_files_only does a live HF Hub round-trip (config.json,
        # tokenizer_config.json, model tree listing, ...) on every cold
        # load even though the tokenizer is already cached locally. On
        # this box that round-trip alone measured ~19s (the model files
        # are on disk; only the online check is slow), and every dev
        # hot-reload wipes this lru_cache, so the *next* real user request
        # after any code edit silently ate ~19s of a 30s total request
        # budget before retrieval had even returned — starving lexical
        # search and, downstream, the LLM generation call of any time left.
        return AutoTokenizer.from_pretrained(model_name, local_files_only=True)
    except Exception:
        return AutoTokenizer.from_pretrained(model_name)


def _encode_token_sparse(text: str) -> SparseVector:
    tokenizer = _load_tokenizer()
    token_ids = tokenizer.encode(text or "", add_special_tokens=False)
    if not token_ids:
        return SparseVector(indices=[], values=[])

    tf = Counter(token_ids)
    indices = sorted(tf.keys())
    values = [float(1.0 + math.log(tf[token_id])) for token_id in indices]
    return SparseVector(indices=indices, values=values)


class BgeM3SparseEncoder:
    """Sparse leg aligned to the active dense embed model tokenizer."""

    encoder_id = "bge_m3"

    def encode_document(self, text: str) -> SparseVector:
        return _encode_token_sparse(text)

    def encode_query(self, text: str) -> SparseVector:
        return _encode_token_sparse(text)

    def encode_documents(self, texts: list[str]) -> list[SparseVector]:
        return [_encode_token_sparse(text) for text in texts]
