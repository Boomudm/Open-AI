"""Retrieval package — intent routing, vector+lexical fusion, degradation (Phase 7)."""

from spark.retrieval.kernel import RAGKernel, RAGKernelInput, RAGKernelOutput, get_rag_kernel

__all__ = [
    "RAGKernel",
    "RAGKernelInput",
    "RAGKernelOutput",
    "get_rag_kernel",
]
