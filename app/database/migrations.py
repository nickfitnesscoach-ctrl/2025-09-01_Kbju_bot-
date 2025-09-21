"""Database migration helpers."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from sqlalchemy.engine import make_url

logger = logging.getLogger(__name__)

_USERS_TABLE = "users"
_DROP_COLUMNS = {"drip_stage_stalled", "drip_stage_tips"}


def _quote_identifier(identifier: str) -> str:
    """Quote SQLite identifiers using double quotes."""

    return '"' + identifier.replace('"', '""') + '"'


def migrate_drop_drip_columns(db_url: str) -> None:
    """Drop legacy DRIP columns from the ``users`` table if they exist."""

    try:
        url = make_url(db_url)
    except Exception as exc:  # noqa: BLE001 - defensive: malformed URL
        logger.warning("[migrate] users: skip, failed to parse DB URL %s: %s", db_url, exc)
        return

    backend = url.get_backend_name()
    if backend != "sqlite":
        logger.debug("[migrate] users: skip, backend %s is not SQLite", backend)
        return

    database = url.database
    if not database:
        logger.warning("[migrate] users: skip, SQLite database path is empty")
        return

    db_path = Path(database)

    try:
        conn = sqlite3.connect(database)
    except sqlite3.Error as exc:
        logger.warning("[migrate] users: skip, cannot open SQLite database %s: %s", database, exc)
        return

    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=OFF")

        columns_to_drop, columns_snapshot = _detect_columns_to_drop(conn)
        if not columns_to_drop:
            logger.info("[migrate] users: skip, columns already absent")
            return

        backup_path = _backup_database_file(db_path)
        if backup_path:
            logger.info("[migrate] users: backup created at %s", backup_path)
        else:
            logger.warning("[migrate] users: backup skipped; file %s not found", db_path)

        sqlite_version = _detect_sqlite_version(conn)
        logger.info(
            "[migrate] users: drop drip_stage_stalled/tips - starting | columns=%s | sqlite_version=%s",
            ", ".join(sorted(columns_to_drop)),
            sqlite_version,
        )

        if _sqlite_supports_drop(sqlite_version):
            if _attempt_drop_columns(conn, sorted(columns_to_drop)):
                logger.info(
                    "[migrate] users: method=ALTER TABLE DROP COLUMN (SQLite %s) - OK",
                    sqlite_version,
                )
                _log_current_columns(conn)
                return
            logger.info("[migrate] users: ALTER TABLE DROP COLUMN failed, fallback to recreate")

        # Refresh snapshot before recreate in case schema changed during failed attempt
        columns_snapshot = _snapshot_table_info(conn)
        _recreate_table_without_columns(conn, columns_snapshot, columns_to_drop, sqlite_version)
        logger.info(
            "[migrate] users: method=recreate table (SQLite %s) - OK",
            sqlite_version,
        )
        _log_current_columns(conn)
    finally:
        try:
            conn.execute("PRAGMA foreign_keys=ON")
        except sqlite3.Error:
            pass
        conn.close()


def _detect_columns_to_drop(conn: sqlite3.Connection) -> tuple[set[str], list[sqlite3.Row]]:
    columns_snapshot = _snapshot_table_info(conn)
    present = {row["name"] for row in columns_snapshot}
    columns_to_drop = present.intersection(_DROP_COLUMNS)
    return columns_to_drop, columns_snapshot


def _snapshot_table_info(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    cursor = conn.execute(f"PRAGMA table_info({_quote_identifier(_USERS_TABLE)})")
    return cursor.fetchall()


def _log_current_columns(conn: sqlite3.Connection) -> None:
    snapshot = _snapshot_table_info(conn)
    column_names = [row["name"] for row in snapshot]
    logger.info("[migrate] users: columns after migration -> %s", column_names)


def _backup_database_file(db_path: Path) -> Path | None:
    if not db_path.exists():
        return None

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.bak.{timestamp}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def _detect_sqlite_version(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT sqlite_version() AS version").fetchone()
    return row["version"] if isinstance(row, sqlite3.Row) else row[0]


def _sqlite_supports_drop(version: str) -> bool:
    parts: list[int] = []
    for token in version.split("."):
        try:
            parts.append(int(token))
        except ValueError:
            break
        if len(parts) == 3:
            break

    while len(parts) < 3:
        parts.append(0)

    major, minor, patch = parts[:3]
    return (major, minor, patch) >= (3, 35, 0)


def _attempt_drop_columns(conn: sqlite3.Connection, columns: Sequence[str]) -> bool:
    try:
        conn.execute("BEGIN")
        alter_template = (
            f"ALTER TABLE {_quote_identifier(_USERS_TABLE)} DROP COLUMN {{column}}"
        )
        for column in columns:
            conn.execute(alter_template.format(column=_quote_identifier(column)))
        conn.commit()
        return True
    except sqlite3.OperationalError as exc:
        logger.info("[migrate] users: ALTER TABLE DROP COLUMN error: %s", exc)
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        return False
    except sqlite3.DatabaseError as exc:
        logger.exception("[migrate] users: unexpected error while dropping columns: %s", exc)
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise


def _recreate_table_without_columns(
    conn: sqlite3.Connection,
    columns_snapshot: Iterable[sqlite3.Row],
    columns_to_drop: set[str],
    sqlite_version: str,
) -> None:
    keep_columns = [
        row for row in columns_snapshot if row["name"] not in columns_to_drop
    ]
    if not keep_columns:
        raise RuntimeError("[migrate] users: cannot recreate table without columns")

    column_definitions = [
        _build_column_definition(row)
        for row in sorted(keep_columns, key=lambda item: item["cid"])
    ]

    unique_constraints, indexes_sql = _snapshot_indexes(conn, columns_to_drop)
    for constraint_columns in unique_constraints:
        quoted = ", ".join(_quote_identifier(column) for column in constraint_columns)
        column_definitions.append(f"UNIQUE ({quoted})")

    new_table_name = f"{_USERS_TABLE}_new"
    create_sql = (
        f"CREATE TABLE {_quote_identifier(new_table_name)} (\n    "
        + ",\n    ".join(column_definitions)
        + "\n)"
    )

    ordered_columns = [
        row["name"] for row in sorted(keep_columns, key=lambda item: item["cid"])
    ]
    columns_csv = ", ".join(_quote_identifier(name) for name in ordered_columns)

    try:
        conn.execute("BEGIN")
        conn.execute(create_sql)
        conn.execute(
            "INSERT INTO {new_table} ({columns}) SELECT {columns} FROM {old_table}".format(
                new_table=_quote_identifier(new_table_name),
                columns=columns_csv,
                old_table=_quote_identifier(_USERS_TABLE),
            )
        )
        conn.execute(f"DROP TABLE {_quote_identifier(_USERS_TABLE)}")
        conn.execute(
            "ALTER TABLE {new_table} RENAME TO {old_table}".format(
                new_table=_quote_identifier(new_table_name),
                old_table=_quote_identifier(_USERS_TABLE),
            )
        )
        for index_sql in indexes_sql:
            conn.execute(index_sql)
        conn.commit()
    except sqlite3.DatabaseError as exc:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        logger.exception(
            "[migrate] users: recreate table failed (SQLite %s): %s", sqlite_version, exc
        )
        raise


def _build_column_definition(column: sqlite3.Row) -> str:
    pieces: list[str] = [_quote_identifier(column["name"])]
    column_type = column["type"]
    if column_type:
        pieces.append(column_type)
    if column["notnull"]:
        pieces.append("NOT NULL")
    default_value = column["dflt_value"]
    if default_value is not None:
        pieces.append(f"DEFAULT {default_value}")
    if column["pk"]:
        pieces.append("PRIMARY KEY")
    return " ".join(pieces)


def _snapshot_indexes(
    conn: sqlite3.Connection,
    columns_to_drop: set[str],
) -> tuple[list[list[str]], list[str]]:
    unique_constraints: list[list[str]] = []
    indexes_sql: list[str] = []

    cursor = conn.execute(f"PRAGMA index_list({_quote_identifier(_USERS_TABLE)})")
    for index_row in cursor.fetchall():
        name = index_row["name"]
        unique = bool(index_row["unique"])
        origin = index_row["origin"]

        info_cursor = conn.execute(
            f"PRAGMA index_info({_quote_identifier(name)})"
        )
        index_columns = [info_row["name"] for info_row in info_cursor.fetchall()]
        if not index_columns or any(col in columns_to_drop for col in index_columns):
            continue

        sql_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            (name,),
        ).fetchone()
        sql_definition = sql_row["sql"] if isinstance(sql_row, sqlite3.Row) else (sql_row[0] if sql_row else None)

        if sql_definition:
            indexes_sql.append(sql_definition)
        elif unique and origin == "u":
            unique_constraints.append(index_columns)

    return unique_constraints, indexes_sql
