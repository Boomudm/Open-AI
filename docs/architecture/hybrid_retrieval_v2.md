# Hybrid Retrieval v2 Architecture

## Overview

Hybrid retrieval v2 combines dense vector search with sparse lexical search via reciprocal rank fusion.

## Components

- **Vector search** — Qdrant nearest-neighbor lookup
- **Lexical search** — Postgres full-text search mirror
- **Fusion** — reciprocal rank fusion of both result sets
- **Reranking** — cross-encoder reranker with diversity filter

## Filter Dimensions

Filter dimensions are shared between Qdrant and Postgres mirrors per the RAG payload contract.
