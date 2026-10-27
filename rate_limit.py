"""Database-backed fixed-window rate limiting."""

import time

from database import get_db


def consume_rate_limit(client_key, limit, window_seconds, now=None):
    """Record one request and return whether it is within the configured window."""
    current_time = int(now if now is not None else time.time())
    window_started_at = current_time - (current_time % window_seconds)

    # Keep the small rate-limit table from accumulating expired hourly buckets.
    connection = get_db()
    connection.execute(
        "DELETE FROM rate_limits WHERE window_started_at < %s",
        (window_started_at - window_seconds,),
    )
    row = connection.execute(
        """INSERT INTO rate_limits (client_key, window_started_at, request_count)
        VALUES (%s, %s, 1)
        ON CONFLICT (client_key, window_started_at)
        DO UPDATE SET request_count = rate_limits.request_count + 1
        RETURNING request_count""",
        (client_key, window_started_at),
    ).fetchone()
    connection.commit()
    return row["request_count"] <= limit
