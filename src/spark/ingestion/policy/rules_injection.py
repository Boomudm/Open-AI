"""Re-export normalize for legacy import path."""

from spark.ingestion.trust.normalize import normalize_policy_text
from spark.ingestion.trust.rules_injection import scan_injection_patterns

__all__ = ["normalize_policy_text", "scan_injection_patterns"]
