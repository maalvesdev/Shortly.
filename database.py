"""PostgreSQL connection and schema helpers."""

import psycopg
from flask import current_app, g
from psycopg.rows import dict_row

SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS urls (
    short_code TEXT PRIMARY KEY,
    original_url TEXT NOT NULL,
    expires_at INTEGER
)""",
    "CREATE INDEX IF NOT EXISTS idx_urls_expires_at ON urls (expires_at)",
    """CREATE TABLE IF NOT EXISTS rate_limits (
        client_key TEXT NOT NULL,
        window_started_at BIGINT NOT NULL,
        request_count INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (client_key, window_started_at)
    )""",
)


def get_db():
    """Return a request-scoped PostgreSQL connection."""
    if "db" not in g:
        g.db = psycopg.connect(current_app.config["DATABASE_URL"], row_factory=dict_row)
    return g.db


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db():
    connection = get_db()
    for statement in SCHEMA_STATEMENTS:
        connection.execute(statement)
    connection.commit()
