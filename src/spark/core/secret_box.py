"""Symmetric encryption for stored secrets (external DB passwords).

Restored for the external data-source Text-to-SQL feature. Keys derive from
``settings.data_source_encryption_key`` (falling back to ``settings.jwt_secret``)
so no new secret has to be provisioned for existing deployments.
"""

from __future__ import annotations

import base64
import hashlib

from spark.core.config import settings


def _encryption_material() -> str:
    explicit = (settings.data_source_encryption_key or "").strip()
    if explicit:
        return explicit
    return settings.jwt_secret


def _derive_key(material: str) -> bytes:
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(plaintext: str) -> str:
    key = _derive_key(_encryption_material())
    data = plaintext.encode("utf-8")
    xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.urlsafe_b64encode(xored).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    key = _derive_key(_encryption_material())
    raw = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
    plain = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    return plain.decode("utf-8")
