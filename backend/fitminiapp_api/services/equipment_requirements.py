from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.services.exercise_catalog import _source_exercise_slug
from fitminiapp_api.services.exercise_catalog_metadata import CANONICAL_EXERCISE_REDIRECTS

# shortcut: unreviewed equipment stays unknown; extend when complete requirements are verified.
_REQUIREMENTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "bench-press": ("barbell", ("bench", "rack")),
    "incline-bench-press": ("barbell", ("bench", "rack")),
    "decline-bench-press": ("barbell", ("bench", "rack")),
    "close-grip-bench-press": ("barbell", ("bench", "rack")),
    "dumbbell-bench-press": ("dumbbell", ("bench",)),
    "incline-dumbbell-press": ("dumbbell", ("bench",)),
    "decline-dumbbell-press": ("dumbbell", ("bench",)),
    "dumbbell-fly": ("dumbbell", ("bench",)),
    "incline-dumbbell-fly": ("dumbbell", ("bench",)),
    "chest-supported-dumbbell-row": ("dumbbell", ("bench",)),
    "incline-dumbbell-curl": ("dumbbell", ("bench",)),
    "lying-dumbbell-triceps-extension": ("dumbbell", ("bench",)),
    "hip-thrust": ("barbell", ("bench",)),
    "bench-dip": ("bodyweight", ("bench",)),
    "pull-up": ("bodyweight", ("pullup_bar",)),
    "chin-up": ("bodyweight", ("pullup_bar",)),
    "hanging-leg-raise": ("bodyweight", ("pullup_bar",)),
    "dead-hang": ("bodyweight", ("pullup_bar",)),
    "chest-dip": ("bodyweight", ("dip_bars",)),
    "squat": ("barbell", ("rack",)),
    "front-squat": ("barbell", ("rack",)),
    "bodyweight-squat": ("bodyweight", ()),
    "bodyweight-glute-bridge": ("bodyweight", ()),
    "single-leg-calf-raise": ("bodyweight", ()),
    "mountain-climber": ("bodyweight", ()),
    "hollow-hold": ("bodyweight", ()),
    "bear-crawl": ("bodyweight", ()),
    "pistol-squat": ("bodyweight", ()),
    "outdoor-run": ("bodyweight", ()),
    "outdoor-walk": ("bodyweight", ()),
    "push-up": ("bodyweight", ()),
    "plank": ("bodyweight", ()),
    "side-plank": ("bodyweight", ()),
    "crunch": ("bodyweight", ()),
    "reverse-crunch": ("bodyweight", ()),
    "dead-bug": ("bodyweight", ()),
    "bird-dog": ("bodyweight", ()),
    "burpee": ("bodyweight", ()),
    "goblet-squat": ("kettlebell", ()),
    "kettlebell-swing": ("kettlebell", ()),
    "kettlebell-clean": ("kettlebell", ()),
    "kettlebell-snatch": ("kettlebell", ()),
    "turkish-get-up": ("kettlebell", ()),
    "suitcase-carry": ("kettlebell", ()),
    "dumbbell-curl": ("dumbbell", ()),
    "hammer-curl": ("dumbbell", ()),
    "dumbbell-lateral-raise": ("dumbbell", ()),
    "dumbbell-front-raise": ("dumbbell", ()),
    "dumbbell-shrug": ("dumbbell", ()),
    "rear-delt-fly": ("dumbbell", ()),
    "renegade-row": ("dumbbell", ()),
    "farmer-walk": ("dumbbell", ()),
    "lunge": ("dumbbell", ()),
    "walking-lunge": ("dumbbell", ()),
    "reverse-lunge": ("dumbbell", ()),
    "split-squat": ("dumbbell", ()),
    "deadlift": ("barbell", ()),
    "sumo-deadlift": ("barbell", ()),
    "romanian-deadlift": ("barbell", ()),
    "barbell-row": ("barbell", ()),
    "pendlay-row": ("barbell", ()),
    "barbell-shrug": ("barbell", ()),
    "reverse-curl": ("barbell", ()),
    "barbell-wrist-curl": ("barbell", ()),
    "barbell-wrist-extension": ("barbell", ()),
    "floor-press": ("barbell", ()),
    "barbell-curl": ("barbell", ()),
}


def exercise_equipment_requirements(exercise: Exercise) -> list[str] | None:
    if exercise.created_by_user_id is not None and exercise.source_exercise_id is None:
        return None
    slug = _source_exercise_slug(exercise)
    requirement = _REQUIREMENTS.get(CANONICAL_EXERCISE_REDIRECTS.get(slug, slug))
    if requirement is None:
        return None
    primary, additional = requirement
    actual = {link.equipment.identifier for link in exercise.equipment_links}
    if actual != {primary}:
        return None
    return sorted(({primary} - {"bodyweight"}) | set(additional))
