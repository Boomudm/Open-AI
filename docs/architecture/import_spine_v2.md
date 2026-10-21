# Import Spine v2 Architecture

## Overview

The import spine v2 defines the canonical module boundaries for the Spark RAG pipeline.

## Module Layout

- `spark.ingestion` — document parsing, chunking, embedding, and index writes
- `spark.retrieval` — vector search, lexical search, fusion, reranking
- `spark.generation` — prompt assembly, streaming, citation extraction

## Design Decisions

- Single `rag_service` facade for backward compatibility
- Native ingest backend only (RAGFlow removed)
- Typed `ParsedRecord` contract between parser and indexer
