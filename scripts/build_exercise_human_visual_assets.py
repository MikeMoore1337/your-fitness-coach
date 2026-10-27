"""Build Task 120E responsive exercise-guide derivatives from reviewed masters.

Source masters are review artifacts and are intentionally not committed. The
checked-in review lock binds every production derivative to the exact reviewed
master hash, visual variant and human-review verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from PIL import Image

ROOT_DIR = Path(__file__).resolve().parents[1]
ASSET_VERSION = "120e-v1"
CREATED_AT = "2026-08-31"
DERIVATIVES = ((480, 320, 82), (768, 512, 84), (1280, 853, 84))


@dataclass(frozen=True)
class HumanVisualSpec:
    variant_key: str
    source_revision: int = 1


HUMAN_VISUAL_SPECS = {
    "chest-supported-dumbbell-row": HumanVisualSpec("canonical_bilateral_incline_bench_dumbbell"),
    "independent-lever-chest-press": HumanVisualSpec(
        "canonical_bilateral_plate_loaded_independent"
    ),
    "independent-lever-lat-pulldown": HumanVisualSpec(
        "canonical_bilateral_plate_loaded_independent"
    ),
    "independent-lever-shoulder-press": HumanVisualSpec(
        "canonical_bilateral_plate_loaded_independent"
    ),
    "lever-high-row": HumanVisualSpec("canonical_bilateral_plate_loaded_high_row"),
    "lever-low-row": HumanVisualSpec("canonical_bilateral_plate_loaded_low_row"),
    "machine-decline-chest-press": HumanVisualSpec("canonical_bilateral_selectorized_decline"),
    "machine-glute-kickback": HumanVisualSpec(
        "canonical_unilateral_standing_lever_footplate", source_revision=2
    ),
    "machine-hip-thrust": HumanVisualSpec("canonical_bilateral_plate_loaded_lap_pad"),
    "machine-incline-chest-press": HumanVisualSpec("canonical_bilateral_selectorized_incline"),
    "machine-pullover": HumanVisualSpec("canonical_bilateral_selectorized_elbow_pad"),
    "machine-triceps-extension": HumanVisualSpec("canonical_bilateral_selectorized_elbow_pad"),
    "pendulum-squat": HumanVisualSpec("canonical_bilateral_plate_loaded_pendulum"),
    "plate-loaded-leg-press": HumanVisualSpec("canonical_bilateral_plate_loaded_sled"),
    "reverse-hyperextension": HumanVisualSpec("canonical_bilateral_plate_loaded_reverse_hyper"),
    "smith-split-squat": HumanVisualSpec("canonical_unilateral_smith_floor_rear_foot"),
    "unilateral-leg-press": HumanVisualSpec("canonical_unilateral_plate_loaded_sled"),
    "v-squat-machine": HumanVisualSpec("canonical_bilateral_plate_loaded_v_squat"),
}

PHASES = ("concentric_end", "eccentric_end")
EXPECTED_OWNER_GATES = {
    "gate_a": "APPROVE_120E_VISUAL_DIRECTION",
    "gate_b": "APPROVE_120E_EXACT_ASSET_REVISION",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def set_digest(records: list[tuple[str, str]]) -> str:
    payload = "".join(f"{name}\0{digest}\n" for name, digest in sorted(records))
    return hashlib.sha256(payload.encode()).hexdigest()


def load_review_lock(lock_path: Path) -> dict:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("schema_version") != 1 or lock.get("asset_version") != ASSET_VERSION:
        raise ValueError("Unsupported Task 120E human-review lock")
    if lock.get("review_record_kind") != "human_review_exact_revision":
        raise ValueError("Task 120E lock is not an explicit human-review record")
    if lock.get("automated_semantic_approval") is not False:
        raise ValueError("Automated semantic approval must be explicitly disabled")
    owner_gates = lock.get("owner_gates", {})
    for gate_id, expected_verdict in EXPECTED_OWNER_GATES.items():
        gate = owner_gates.get(gate_id, {})
        if gate.get("status") != "approved" or gate.get("verdict") != expected_verdict:
            raise ValueError(
                f"Task 120E {gate_id.replace('_', ' ').title()} exact verdict is not approved"
            )
    if set(lock.get("exercises", {})) != set(HUMAN_VISUAL_SPECS):
        raise ValueError("Task 120E human-review lock exercise coverage mismatch")
    return lock


def build(source_dir: Path, asset_dir: Path, lock_path: Path) -> dict:
    lock = load_review_lock(lock_path)
    source_records: list[tuple[str, str]] = []
    derivative_records: list[tuple[str, str]] = []
    staging_parent = ROOT_DIR / ".artifacts" / "runtime" / "tmp"
    staging_parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix="exercise-human-visuals-", dir=staging_parent) as temporary:
        staging_dir = Path(temporary)
        for slug, spec in sorted(HUMAN_VISUAL_SPECS.items()):
            locked_exercise = lock["exercises"][slug]
            if locked_exercise["variant_key"] != spec.variant_key:
                raise ValueError(f"Variant mismatch for {slug}")
            for phase_id in PHASES:
                locked_phase = locked_exercise["phases"][phase_id]
                source_name = f"{slug}-{phase_id}-v{spec.source_revision}.png"
                source_path = source_dir / source_name
                if not source_path.is_file():
                    raise ValueError(f"Missing reviewed source master: {source_path}")
                with Image.open(source_path) as master:
                    master.load()
                    if master.size != (1536, 1024):
                        raise ValueError(
                            f"Unexpected master dimensions for {source_name}: {master.size}"
                        )
                    rgb = master.convert("RGB")
                master_digest = sha256(source_path)
                if locked_phase["source_master_filename"] != source_name:
                    raise ValueError(f"Source filename is not human-reviewed: {source_name}")
                if locked_phase["source_master_sha256"] != master_digest:
                    raise ValueError(f"Source master is not the reviewed revision: {source_name}")
                required_reviews = {
                    "domain": "pass",
                    "anatomy": "pass",
                    "equipment": "pass",
                    "phase": "pass",
                    "visual_style": "pass",
                    "mobile": "pass",
                    "legal": "pass_with_limitations",
                }
                if any(
                    locked_phase["reviews"].get(key) != value
                    for key, value in required_reviews.items()
                ):
                    raise ValueError(f"Human review is incomplete for {slug}/{phase_id}")
                source_records.append((source_name, master_digest))

                sources: list[dict] = []
                for width, height, quality in DERIVATIVES:
                    relative_path = Path("human-v1") / slug / f"{phase_id}-{width}w.webp"
                    output_path = staging_dir / relative_path
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    resized = rgb.resize((width, height), Image.Resampling.LANCZOS)
                    resized.save(
                        output_path,
                        "WEBP",
                        quality=quality,
                        method=6,
                        exact=True,
                        exif=b"",
                    )
                    with Image.open(output_path) as derivative:
                        derivative.load()
                        if derivative.size != (width, height) or derivative.format != "WEBP":
                            raise ValueError(f"Invalid derivative: {output_path}")
                    derivative_digest = sha256(output_path)
                    relative = relative_path.as_posix()
                    derivative_records.append((relative, derivative_digest))
                    sources.append(
                        {
                            "path": relative,
                            "mime_type": "image/webp",
                            "width": width,
                            "height": height,
                            "byte_size": output_path.stat().st_size,
                            "sha256": derivative_digest,
                        }
                    )
                if sources != locked_phase["sources"]:
                    raise ValueError(
                        f"Derivative output is not the reviewed revision: {slug}/{phase_id}"
                    )

        if set_digest(source_records) != lock["source_set_sha256"]:
            raise ValueError("Source-set digest is not the reviewed revision")
        if set_digest(derivative_records) != lock["derivative_set_sha256"]:
            raise ValueError("Derivative-set digest is not the reviewed revision")

        for relative, _digest in derivative_records:
            destination = asset_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            copyfile(staging_dir / relative, destination)
    return lock


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument(
        "--asset-dir",
        type=Path,
        default=ROOT_DIR / "backend" / "assets" / "exercise-guides",
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=ROOT_DIR / "docs" / "exercises" / "catalog-v2" / "120E_ASSET_REVIEW.json",
    )
    args = parser.parse_args()
    lock = build(args.source_dir, args.asset_dir, args.lock)
    print(
        "Built "
        f"{len(HUMAN_VISUAL_SPECS) * len(PHASES) * len(DERIVATIVES)} derivatives; "
        f"source_set={lock['source_set_sha256']}; "
        f"derivative_set={lock['derivative_set_sha256']}"
    )


if __name__ == "__main__":
    main()
