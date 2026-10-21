"""User token_version and permission role migration

Revision ID: 0022_users_token_version_and_roles
Revises: 0021_job_positions_and_document_acl
Create Date: 2026-06-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022_token_version_roles"
down_revision: Union[str, None] = "0021_job_positions_acl"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )

    conn = op.get_bind()

    for code, desc in (
        ("employee", "Floor worker — chat and document upload"),
        ("operator", "Supervisor / operator — dashboard and insights"),
    ):
        conn.execute(
            sa.text(
                "INSERT INTO roles (role_code, description) "
                "SELECT :code, :desc WHERE NOT EXISTS "
                "(SELECT 1 FROM roles WHERE role_code = :code)"
            ),
            {"code": code, "desc": desc},
        )

    conn.execute(
        sa.text(
            """
            UPDATE user_roles ur
            SET role_id = (SELECT role_id FROM roles WHERE role_code = 'employee')
            WHERE ur.role_id IN (SELECT role_id FROM roles WHERE role_code = 'viewer')
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE user_roles ur
            SET role_id = (SELECT role_id FROM roles WHERE role_code = 'operator')
            WHERE ur.role_id IN (
                SELECT role_id FROM roles WHERE role_code IN ('engineer', 'technician')
            )
            """
        )
    )

    conn.execute(sa.text("DELETE FROM roles WHERE role_code IN ('viewer', 'engineer', 'technician')"))


def downgrade() -> None:
    conn = op.get_bind()
    for code, desc in (
        ("viewer", "Read-only access"),
        ("engineer", "Read/write machines, components, documents"),
        ("technician", "Read documents, write repair_history"),
    ):
        conn.execute(
            sa.text(
                "INSERT INTO roles (role_code, description) "
                "SELECT :code, :desc WHERE NOT EXISTS "
                "(SELECT 1 FROM roles WHERE role_code = :code)"
            ),
            {"code": code, "desc": desc},
        )

    conn.execute(
        sa.text(
            """
            UPDATE user_roles ur
            SET role_id = (SELECT role_id FROM roles WHERE role_code = 'viewer')
            WHERE ur.role_id = (SELECT role_id FROM roles WHERE role_code = 'employee')
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE user_roles ur
            SET role_id = (SELECT role_id FROM roles WHERE role_code = 'engineer')
            WHERE ur.role_id = (SELECT role_id FROM roles WHERE role_code = 'operator')
            """
        )
    )
    conn.execute(sa.text("DELETE FROM roles WHERE role_code IN ('employee', 'operator')"))
    op.drop_column("users", "token_version")
