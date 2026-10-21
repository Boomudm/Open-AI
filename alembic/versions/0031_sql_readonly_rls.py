"""Text-to-SQL: read-only role + factory Row-Level Security (RLS).

Revision ID: 0031_sql_readonly_rls
Revises: 0030_shadow_routing_log
Create Date: 2026-06-19

Creates ``spark_sql_readonly`` (SELECT-only on analytics tables, default
``transaction_read_only``) and RLS policies keyed on session GUCs:

- ``app.rls_bypass`` — ``on`` for unrestricted admin analytics
- ``app.factory_ids`` — comma-separated tenant allow-list
- ``app.machine_id`` — optional machine filter

Password/user override via ``POSTGRES_SQL_READONLY_PASSWORD`` /
``POSTGRES_SQL_READONLY_USER`` at migration time (must match app ``.env``).
"""

from __future__ import annotations

import os
from typing import Sequence, Union

from alembic import op

from spark.core.config import settings

revision: str = "0031_sql_readonly_rls"
down_revision: Union[str, None] = "0030_shadow_routing_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

READONLY_USER = os.environ.get("POSTGRES_SQL_READONLY_USER", "spark_sql_readonly")
READONLY_PASSWORD = os.environ.get(
    "POSTGRES_SQL_READONLY_PASSWORD",
    "spark_sql_readonly_dev",
)
STATEMENT_TIMEOUT_MS = os.environ.get("SQL_STATEMENT_TIMEOUT_MS", "8000")

# Must stay in sync with spark.services.analytics_service.ALLOWED_TABLES
ANALYTICS_TABLES = (
    "factories",
    "machines",
    "machine_aliases",
    "components",
    "component_aliases",
    "work_orders",
    "repair_history",
    "documents",
    "inspections",
    "incidents",
    "spare_parts",
    "stock_movements",
    "purchase_orders",
    "po_lines",
)

FACTORY_DIRECT_TABLES = ("factories", "machines")
MACHINE_LINKED_TABLES = (
    "machine_aliases",
    "components",
    "repair_history",
    "inspections",
    "incidents",
)
WORK_ORDERS_TABLE = "work_orders"
DOCUMENTS_TABLE = "documents"
COMPONENT_ALIASES_TABLE = "component_aliases"
GLOBAL_INVENTORY_TABLES = ("spare_parts", "purchase_orders", "po_lines", "stock_movements")


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _create_rls_functions() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION spark_rls_bypass() RETURNS boolean AS $$
          SELECT coalesce(nullif(current_setting('app.rls_bypass', true), ''), 'off') = 'on';
        $$ LANGUAGE sql STABLE;

        CREATE OR REPLACE FUNCTION spark_rls_factory_ids() RETURNS text[] AS $$
          SELECT CASE
            WHEN coalesce(nullif(current_setting('app.factory_ids', true), ''), '') = ''
              THEN ARRAY[]::text[]
            ELSE string_to_array(current_setting('app.factory_ids', true), ',')
          END;
        $$ LANGUAGE sql STABLE;

        CREATE OR REPLACE FUNCTION spark_rls_machine_id() RETURNS text AS $$
          SELECT nullif(current_setting('app.machine_id', true), '');
        $$ LANGUAGE sql STABLE;

        CREATE OR REPLACE FUNCTION spark_rls_factory_allowed(p_factory_id text) RETURNS boolean AS $$
          SELECT spark_rls_bypass()
            OR (
              p_factory_id IS NOT NULL
              AND p_factory_id = ANY(spark_rls_factory_ids())
            );
        $$ LANGUAGE sql STABLE;

        CREATE OR REPLACE FUNCTION spark_rls_machine_allowed(p_machine_id text) RETURNS boolean AS $$
          SELECT spark_rls_bypass()
            OR (
              p_machine_id IS NOT NULL
              AND EXISTS (
                SELECT 1
                FROM machines m
                WHERE m.machine_id = p_machine_id
                  AND spark_rls_factory_allowed(m.factory_id)
              )
              AND (
                spark_rls_machine_id() IS NULL
                OR p_machine_id = spark_rls_machine_id()
              )
            );
        $$ LANGUAGE sql STABLE;

        CREATE OR REPLACE FUNCTION spark_rls_component_allowed(p_component_id text) RETURNS boolean AS $$
          SELECT spark_rls_bypass()
            OR EXISTS (
              SELECT 1
              FROM components c
              JOIN machines m ON m.machine_id = c.machine_id
              WHERE c.component_id = p_component_id
                AND spark_rls_factory_allowed(m.factory_id)
                AND (
                  spark_rls_machine_id() IS NULL
                  OR m.machine_id = spark_rls_machine_id()
                )
            );
        $$ LANGUAGE sql STABLE;

        CREATE OR REPLACE FUNCTION spark_rls_has_factory_access() RETURNS boolean AS $$
          SELECT spark_rls_bypass() OR cardinality(spark_rls_factory_ids()) > 0;
        $$ LANGUAGE sql STABLE;
        """
    )


def _drop_rls_functions() -> None:
    for fn in (
        "spark_rls_has_factory_access()",
        "spark_rls_component_allowed(text)",
        "spark_rls_machine_allowed(text)",
        "spark_rls_factory_allowed(text)",
        "spark_rls_machine_id()",
        "spark_rls_factory_ids()",
        "spark_rls_bypass()",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {fn};")


def _create_readonly_role() -> None:
    user = READONLY_USER
    pwd = _quote_literal(READONLY_PASSWORD)
    timeout_ms = int(STATEMENT_TIMEOUT_MS)
    db_name = settings.postgres_db
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{user}') THEN
            CREATE ROLE {user} WITH LOGIN PASSWORD {pwd};
          END IF;
        END
        $$;
        """
    )
    op.execute(f"ALTER ROLE {user} SET statement_timeout = {timeout_ms}")
    op.execute(f"ALTER ROLE {user} SET default_transaction_read_only = on")
    op.execute(f'GRANT CONNECT ON DATABASE "{db_name}" TO {user}')
    op.execute(f"GRANT USAGE ON SCHEMA public TO {user}")
    tables_csv = ", ".join(ANALYTICS_TABLES)
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {user}")
    op.execute(f"GRANT SELECT ON {tables_csv} TO {user}")
    for fn in (
        "spark_rls_bypass()",
        "spark_rls_factory_ids()",
        "spark_rls_machine_id()",
        "spark_rls_factory_allowed(text)",
        "spark_rls_machine_allowed(text)",
        "spark_rls_component_allowed(text)",
        "spark_rls_has_factory_access()",
    ):
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO {user}")


def _revoke_readonly_role() -> None:
    user = READONLY_USER
    db_name = settings.postgres_db
    tables_csv = ", ".join(ANALYTICS_TABLES)
    op.execute(f"REVOKE SELECT ON {tables_csv} FROM {user}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {user}")
    op.execute(f'REVOKE CONNECT ON DATABASE "{db_name}" FROM {user}')
    op.execute(f"DROP ROLE IF EXISTS {user}")


def _enable_table_rls(table: str, policy_sql: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS spark_rls_select ON {table}")
    op.execute(
        f"CREATE POLICY spark_rls_select ON {table} FOR SELECT TO {READONLY_USER} "
        f"USING ({policy_sql})"
    )


def _disable_table_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS spark_rls_select ON {table}")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    _create_rls_functions()
    _create_readonly_role()

    for table in FACTORY_DIRECT_TABLES:
        _enable_table_rls(table, "spark_rls_factory_allowed(factory_id)")

    for table in MACHINE_LINKED_TABLES:
        _enable_table_rls(table, "spark_rls_machine_allowed(machine_id)")

    _enable_table_rls(
        WORK_ORDERS_TABLE,
        """
        (
          spark_rls_bypass()
          OR (
            factory_id IS NOT NULL
            AND spark_rls_factory_allowed(factory_id)
          )
          OR (
            factory_id IS NULL
            AND spark_rls_machine_allowed(machine_id)
          )
        )
        AND (
          spark_rls_machine_id() IS NULL
          OR machine_id = spark_rls_machine_id()
        )
        """.strip(),
    )

    _enable_table_rls(
        DOCUMENTS_TABLE,
        """
        (
          spark_rls_bypass()
          OR (
            factory_id IS NOT NULL
            AND spark_rls_factory_allowed(factory_id)
          )
          OR (
            factory_id IS NULL
            AND machine_id IS NOT NULL
            AND spark_rls_machine_allowed(machine_id)
          )
        )
        AND (
          spark_rls_machine_id() IS NULL
          OR machine_id IS NULL
          OR machine_id = spark_rls_machine_id()
        )
        """.strip(),
    )

    _enable_table_rls(
        COMPONENT_ALIASES_TABLE,
        "spark_rls_component_allowed(component_id)",
    )

    for table in GLOBAL_INVENTORY_TABLES:
        _enable_table_rls(table, "spark_rls_has_factory_access()")


def downgrade() -> None:
    for table in reversed(ANALYTICS_TABLES):
        _disable_table_rls(table)
    _revoke_readonly_role()
    _drop_rls_functions()
