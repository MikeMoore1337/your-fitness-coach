"""Read-only PostgreSQL capacity snapshot inside a legacy active backend.

The trusted host collector uses docker exec <id> python -c with this fixed
reviewed source; credentials remain only inside the already-running container.
This probe does not require a new collector module in that legacy container.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

APPLICATION_NAMES = (
    "yfc-backend",
    "yfc-worker",
    "yfc-setup",
    "yfc-migration",
)


def collect() -> dict[str, object]:
    import psycopg

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise ValueError("missing PostgreSQL connection")
    connect_url = url.replace("postgresql+psycopg://", "postgresql://", 1)
    options = (
        "-c default_transaction_read_only=on "
        "-c statement_timeout=5000 "
        "-c lock_timeout=1000 "
        "-c application_name=yfc-connection-budget-collector"
    )
    # The names are fixed reviewed constants, never user or database input.
    literals = ", ".join(f"'{name}'" for name in APPLICATION_NAMES)
    sql = f"""
SELECT
    current_setting('server_version_num')::int,
    current_setting('max_connections')::int,
    current_setting('superuser_reserved_connections')::int,
    NULLIF(current_setting('reserved_connections', true), '')::int,
    (SELECT count(*)::int FROM pg_stat_activity),
    (SELECT count(*)::int FROM pg_stat_activity WHERE application_name IN ({literals})),
    (SELECT count(*)::int FROM pg_stat_activity
       WHERE application_name IS NULL OR btrim(application_name) = ''),
    (SELECT count(*)::int FROM pg_stat_activity
       WHERE application_name IS NOT NULL
         AND btrim(application_name) <> ''
         AND application_name NOT IN ({literals})),
    pg_has_role(current_user, 'pg_read_all_stats', 'member'),
    current_setting('is_superuser')::boolean
"""
    with (
        psycopg.connect(connect_url, connect_timeout=5, options=options) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(sql)
        row = cursor.fetchone()
    if not isinstance(row, (tuple, list)) or len(row) != 10:
        raise ValueError("invalid snapshot shape")
    if row[8] is not True or row[9] is not False:
        raise ValueError("insufficient non-superuser observation privileges")
    values = row[:8]
    if any(value is None and index != 3 for index, value in enumerate(values)):
        raise ValueError("incomplete observation")
    if any(
        isinstance(value, bool) or (value is not None and (not isinstance(value, int) or value < 0))
        for value in values
    ):
        raise ValueError("invalid observation")
    version, maximum, superuser_reserved, reserved, current, yfc, unattributed, other = values
    if version < 100000 or maximum <= 0 or yfc + unattributed + other != current:
        raise ValueError("unreconciled observation")
    if version >= 160000 and reserved is None:
        raise ValueError("PostgreSQL 16 reserved capacity is unknown")
    if version < 160000 and reserved is not None and reserved != 0:
        raise ValueError("invalid legacy reserved capacity")
    return {
        "status": "PASS",
        "captured_at": datetime.now(UTC).isoformat(),
        "postgres": {
            "server_version_major": version // 10000,
            "max_connections": maximum,
            "superuser_reserved_connections": superuser_reserved,
            "reserved_connections": reserved,
            "current_connections": current,
            "observed_yfc_connections": yfc,
            "observed_non_yfc_connections": other + unattributed,
            "unattributed_connections": unattributed,
        },
    }


if __name__ == "__main__":
    try:
        print(json.dumps(collect(), sort_keys=True))
    except Exception:
        # Never print database URLs, SQL rows, credentials or driver exceptions.
        print('{"status":"BLOCKED"}')
        raise SystemExit(1) from None
