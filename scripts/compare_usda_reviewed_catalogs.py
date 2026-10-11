"""Compare reviewed USDA snapshots without writing to YFC's food database."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from fitminiapp_api.schemas.food import FoodCatalog  # noqa: E402
from fitminiapp_api.services.food_import import load_food_catalog  # noqa: E402


@dataclass(frozen=True)
class CatalogComparison:
    previous: int
    candidate: int
    new_ids: tuple[str, ...]
    removed_ids: tuple[str, ...]
    changed_ids: tuple[str, ...]

    @property
    def safe_for_reviewed_extension(self) -> bool:
        return not self.removed_ids and not self.changed_ids

    def as_dict(self) -> dict[str, object]:
        return {
            "previous": self.previous,
            "candidate": self.candidate,
            "added_count": len(self.new_ids),
            "removed_count": len(self.removed_ids),
            "changed_count": len(self.changed_ids),
            "added_ids": list(self.new_ids),
            "removed_ids": list(self.removed_ids),
            "changed_ids": list(self.changed_ids),
            "safe_for_reviewed_extension": self.safe_for_reviewed_extension,
        }


def compare_catalogs(previous: FoodCatalog, candidate: FoodCatalog) -> CatalogComparison:
    """Reject removals and silent changes to previously published food facts."""

    if previous.source.name != candidate.source.name:
        raise ValueError("USDA provenance/source mismatch")
    if previous.source.license != "CC0-1.0" or candidate.source.license != "CC0-1.0":
        raise ValueError("USDA source license is not verified CC0-1.0")
    prior = {food.external_id: food.model_dump(mode="json") for food in previous.foods}
    next_items = {food.external_id: food.model_dump(mode="json") for food in candidate.foods}
    return CatalogComparison(
        previous=len(prior),
        candidate=len(next_items),
        new_ids=tuple(sorted(next_items.keys() - prior.keys(), key=int)),
        removed_ids=tuple(sorted(prior.keys() - next_items.keys(), key=int)),
        changed_ids=tuple(
            sorted(
                (
                    fdc_id
                    for fdc_id in prior.keys() & next_items.keys()
                    if prior[fdc_id] != next_items[fdc_id]
                ),
                key=int,
            )
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument(
        "--output", type=Path, default=None, help="Write review metrics outside Git"
    )
    args = parser.parse_args()
    report = compare_catalogs(load_food_catalog(args.previous), load_food_catalog(args.candidate))
    payload = json.dumps(report.as_dict(), ensure_ascii=False, indent=2)
    if args.output is not None:
        if args.output.exists():
            parser.error("output already exists")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    if not report.safe_for_reviewed_extension:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
