from __future__ import annotations

from alembic import op
from sqlalchemy import inspect


def table_exists(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def column_exists(table_name: str, column_name: str) -> bool:
    if not table_exists(table_name):
        return False
    return any(column["name"] == column_name for column in inspect(op.get_bind()).get_columns(table_name))


def column_is_nullable(table_name: str, column_name: str) -> bool | None:
    if not table_exists(table_name):
        return None
    for column in inspect(op.get_bind()).get_columns(table_name):
        if column["name"] == column_name:
            return bool(column.get("nullable"))
    return None


def index_exists(table_name: str, index_name: str) -> bool:
    if not table_exists(table_name):
        return False
    return any(index.get("name") == index_name for index in inspect(op.get_bind()).get_indexes(table_name))
