from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse


def build_file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def build_s3_uri(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"


def parse_file_uri(storage_uri: str) -> Path:
    parsed = urlparse(storage_uri)
    if parsed.scheme != "file":
        raise ValueError(f"unsupported storage URI scheme: {storage_uri}")
    return Path(parsed.path)


def parse_s3_uri(storage_uri: str) -> tuple[str, str]:
    parsed = urlparse(storage_uri)
    if parsed.scheme != "s3":
        raise ValueError(f"unsupported storage URI scheme: {storage_uri}")
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        raise ValueError(f"invalid s3 storage URI: {storage_uri}")
    return bucket, key


def is_file_uri(storage_uri: str) -> bool:
    return urlparse(storage_uri).scheme == "file"


def is_s3_uri(storage_uri: str) -> bool:
    return urlparse(storage_uri).scheme == "s3"
