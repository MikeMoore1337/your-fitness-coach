"""Sanitized, opt-in evidence from actual Telegram getUpdates results.

The bot process is the only producer. No Telegram API calls or user/token data are
introduced. An independent restricted reader must still verify source, owner,
freshness and trust before treating this file as operational evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

STATES = frozenset({"healthy", "unhealthy", "unknown"})
EVIDENCE = frozenset({
    "getupdates_success", "getupdates_error", "polling_starting",
    "polling_stopped", "polling_conflict",
})


def write_polling_health(
    path: str, state: str, evidence: str, *, now: datetime | None = None,
) -> bool:
    """Atomic, small, fixed-schema proof. Fail closed without harming polling."""
    if not path:
        return False
    if state not in STATES or evidence not in EVIDENCE:
        raise ValueError("invalid_polling_health_state")
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("timezone_required")
    payload = {
        "schema": 1,
        "source_host": "yfc",
        "component": "telegram_polling",
        "state": state,
        "evidence": evidence,
        "observed_at": observed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    target = Path(path)
    temporary: str | None = None
    try:
        if not target.is_absolute() or target.is_symlink() or target.parent.is_symlink():
            return False
        if not target.parent.is_dir():
            return False
        # No sensitive fields and no persistence unless explicitly provisioned.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent,
            prefix=".polling-status-", delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(payload, handle, separators=(",", ":"), ensure_ascii=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o640)
        os.replace(temporary, target)
        return True
    except OSError:
        return False
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            except OSError:
                pass
