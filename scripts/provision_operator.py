#!/usr/bin/env python3
"""Provision or update a plant operator before first Google sign-in.

Usage:
  python scripts/provision_operator.py \\
    --email worker@yourcompany.co.th \\
    --full-name "สมชาย ใจดี" \\
    --factories F-01,F-02 \\
    --role employee
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import func, select

from spark.core.database import AsyncSessionLocal
from spark.core.logging import configure_logging, get_logger
from spark.db.models.org import Factory, Role, User, UserFactoryAccess, UserRole

configure_logging()
log = get_logger("provision_operator")

_USERNAME_MAX = 50


def _username_base(email: str) -> str:
    local = email.split("@", 1)[0]
    base = re.sub(r"[^a-zA-Z0-9_]", "_", local).strip("_").lower()
    return (base or "user")[: _USERNAME_MAX - 4]


async def _unique_username(session, email: str) -> str:
    base = _username_base(email)
    for n in range(1, 1000):
        if n == 1:
            candidate = base
        else:
            suffix = f"_{n}"
            candidate = f"{base[: _USERNAME_MAX - len(suffix)]}{suffix}"
        exists = await session.scalar(select(User).where(User.username == candidate))
        if not exists:
            return candidate
    raise RuntimeError("could not allocate username")


async def provision(
    *,
    email: str,
    full_name: str | None,
    factories: list[str],
    role_code: str,
) -> User:
    email = email.strip()
    async with AsyncSessionLocal() as session:
        user = await session.scalar(
            select(User).where(func.lower(User.email) == email.lower())
        )
        if user is None:
            user = User(
                username=await _unique_username(session, email),
                full_name=full_name,
                email=email,
                password_hash=None,
                is_active=True,
            )
            session.add(user)
            await session.flush()
            log.info("provision_user_created", user_id=str(user.user_id), email=email)
        else:
            if full_name:
                user.full_name = full_name
            log.info("provision_user_updated", user_id=str(user.user_id), email=email)

        role = await session.scalar(select(Role).where(Role.role_code == role_code))
        if role:
            exists = await session.scalar(
                select(UserRole).where(
                    UserRole.user_id == user.user_id,
                    UserRole.role_id == role.role_id,
                )
            )
            if not exists:
                session.add(UserRole(user_id=user.user_id, role_id=role.role_id))

        for factory_id in factories:
            factory = await session.scalar(
                select(Factory).where(Factory.factory_id == factory_id)
            )
            if not factory:
                log.warning("provision_factory_missing", factory_id=factory_id)
                continue
            exists = await session.scalar(
                select(UserFactoryAccess).where(
                    UserFactoryAccess.user_id == user.user_id,
                    UserFactoryAccess.factory_id == factory_id,
                )
            )
            if not exists:
                session.add(
                    UserFactoryAccess(
                        user_id=user.user_id,
                        factory_id=factory_id,
                        access_level="read",
                    )
                )

        await session.commit()
        await session.refresh(user)
        return user


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision operator for Google OAuth")
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", default="")
    parser.add_argument("--factories", required=True, help="Comma-separated factory IDs")
    parser.add_argument("--role", default="employee", choices=["employee", "operator", "admin"])
    args = parser.parse_args()

    factories = [f.strip() for f in args.factories.split(",") if f.strip()]
    if not factories:
        raise SystemExit("At least one factory is required")

    user = asyncio.run(
        provision(
            email=args.email,
            full_name=args.full_name.strip() or None,
            factories=factories,
            role_code=args.role.strip(),
        )
    )
    log.info("provision_complete", username=user.username, email=user.email)


if __name__ == "__main__":
    main()
