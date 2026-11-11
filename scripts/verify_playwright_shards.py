"""Verify Playwright shard receipts before the required CI result."""

import json
import sys
from collections import Counter
from pathlib import Path

if __package__:
    from scripts.scheduled_regression import FRONTEND_E2E_SHARD_COUNT
else:
    from scheduled_regression import FRONTEND_E2E_SHARD_COUNT


def verify(directory: Path, count: int) -> None:
    files = sorted(directory.glob("*/receipt.json"))
    if len(files) != count:
        raise ValueError(f"Expected {count} receipts, found {len(files)}")
    receipts = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    reference = receipts[0]["all"]
    if not reference or len(reference) != len(set(reference)):
        raise ValueError("Empty or duplicate collection")
    seen = set()
    selected = []
    for receipt in receipts:
        number, total = map(int, receipt["shard"].split("/"))
        if total != count or number not in range(1, count + 1) or number in seen:
            raise ValueError("Invalid or duplicate shard")
        if receipt["all"] != reference or not receipt["selected"]:
            raise ValueError("Shard collection differs or selection is empty")
        seen.add(number)
        selected.extend(receipt["selected"])
    if Counter(selected) != Counter(reference):
        raise ValueError("Shard coverage differs from collection")


if __name__ == "__main__":
    try:
        verify(Path(sys.argv[1]), FRONTEND_E2E_SHARD_COUNT)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        print(f"Playwright shard verification failed: {error}", file=sys.stderr)
        sys.exit(1)
    print("Playwright shard receipts verified")
