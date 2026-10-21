"""ACL materialization and cache invalidation (app-layer Phase 4)."""

from spark.services.acl.cache_invalidation import (
    bump_factory_acl_version,
    invalidate_user_doc_acl_cache,
    read_acl_versions,
    read_factory_acl_version,
    read_user_acl_version,
)
from spark.services.acl.document_acl_cache import allowed_doc_ids_for_principal_cached
from spark.services.acl.mutation_hooks import (
    on_document_positions_changed,
    on_document_released,
    on_user_factory_access_changed,
    on_user_positions_changed,
)

__all__ = [
    "allowed_doc_ids_for_principal_cached",
    "bump_factory_acl_version",
    "invalidate_user_doc_acl_cache",
    "on_document_positions_changed",
    "on_document_released",
    "on_user_factory_access_changed",
    "on_user_positions_changed",
    "read_acl_versions",
    "read_factory_acl_version",
    "read_user_acl_version",
]
