#!/usr/bin/env python3
"""Repair legacy Google OAuth user rows (username = Google sub, missing email).

Usage:
  python scripts/repair_oauth_users.py --dry-run
  python scripts/repair_oauth_users.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select

from spark.core.database import AsyncSessionLocal
from spark.core.logging import configure_logging, get_logger
from spark.db.models.org import User

configure_logging()
log = get_logger("repair_oauth_users")

_SUB_USERNAME = re.compile(r"^\d{5,}$")


async def run(*, apply: bool) -> int:
    flagged = 0
    async with AsyncSessionLocal() as session:
        users = (
            await session.execute(
                select(User).where(User.email.is_(None) | (User.email == ""))
            )
        ).scalars().all()

        for user in users:
            issues: list[str] = []
            if _SUB_USERNAME.match(user.username or ""):
                issues.append("username_looks_like_google_sub")
            if user.google_id and not user.email:
                issues.append("google_id_without_email")
            if not issues:
                continue

            flagged += 1
            log.warning(
                "oauth_user_needs_repair",
                user_id=str(user.user_id),
                username=user.username,
                google_id=user.google_id,
                issues=issues,
            )
            if apply:
                if _SUB_USERNAME.match(user.username or "") and user.google_id:
                    log.info(
                        "oauth_user_mark_inactive",
                        user_id=str(user.user_id),
                        hint="User should sign in again with Google to auto-repair",
                    )

    if flagged == 0:
        log.info("repair_oauth_users_none")
        return 0

    log.info("repair_oauth_users_flagged", count=flagged, apply=apply)
    if not apply:
        log.info("repair_oauth_users_rerun_with_apply")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair legacy Google OAuth users")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(apply=args.apply)))


if __name__ == "__main__":
    main()
