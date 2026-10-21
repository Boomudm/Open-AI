# RAG payload contract

Generated from `src/spark/contracts/rag_payload_contract.py`. Do not edit by hand — update the contract module and re-run contract tests.

## Qdrant ingest payload (`base_payload`)

- `boost_tokens`
- `child_index_in_parent`
- `chunk_id`
- `chunk_index`
- `chunk_level`
- `chunk_schema_version`
- `component_id`
- `config_hash`
- `content_hash`
- `doc_id`
- `document_category`
- `document_type`
- `drawing_no`
- `effective_date`
- `embed_dimension`
- `embed_model`
- `embed_model_id`
- `embed_model_version`
- `embed_provider`
- `expiry_date`
- `extraction_confidence`
- `extraction_source`
- `factory_id`
- `has_tables`
- `ingest_generation`
- `ingest_version`
- `ingested_at`
- `language`
- `machine_id`
- `needs_review`
- `page`
- `page_content`
- `parent_chunk_id`
- `parent_index`
- `restricted_position_ids`
- `retrieval_enabled`
- `revision`
- `revision_sort_key`
- `row_number`
- `section_path`
- `source_file`
- `source_sheet`
- `sparse_encoder_id`
- `src_path`
- `tgt_path`
- `title`

## Qdrant filter dimensions (`_build_qdrant_filter`)

- `doc_id`
- `document_category`
- `document_type`
- `drawing_no`
- `embed_model_version`
- `expiry_date`
- `factory_id`
- `language`
- `machine_id`
- `restricted_position_ids`
- `retrieval_enabled`
- `revision`

## Postgres lexical mirror dimensions (`hybrid.py`)

- `doc_id`
- `document_category`
- `document_type`
- `expiry_date`
- `factory_id`
- `ingest_generation`
- `language`
- `machine_id`
- `retrieval_enabled`

## Invariants

- Every Qdrant filter dimension MUST exist on the ingest payload.
- Postgres mirror dimensions MUST match Qdrant filter dimensions plus `ingest_generation` (active-generation guard).
- Retrieval-only payload keys MUST NOT be required at ingest time.

