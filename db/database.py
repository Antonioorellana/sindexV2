from __future__ import annotations

import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "sindicato.db"
SCHEMA_PATH = Path(__file__).resolve().with_name("schema.sql")


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    target = Path(db_path) if db_path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(db_path: str | Path | None = None) -> Path:
    target = Path(db_path) if db_path else DB_PATH
    with get_connection(target) as connection:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        columns = [row["name"] for row in connection.execute("PRAGMA table_info(audit_log)").fetchall()]
        if columns and "usuario" not in columns:
            connection.execute("ALTER TABLE audit_log ADD COLUMN usuario TEXT DEFAULT ''")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_usuario ON audit_log(usuario)")
        user_columns = [row["name"] for row in connection.execute("PRAGMA table_info(usuarios)").fetchall()]
        if user_columns and "usos_password_inicial" not in user_columns:
            connection.execute("ALTER TABLE usuarios ADD COLUMN usos_password_inicial INTEGER NOT NULL DEFAULT 0")
        if user_columns and "requiere_cambio_password" not in user_columns:
            connection.execute("ALTER TABLE usuarios ADD COLUMN requiere_cambio_password INTEGER NOT NULL DEFAULT 0")
    return target
