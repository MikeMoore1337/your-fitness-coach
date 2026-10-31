"""Owner expression for a workout joined to its program and import provenance."""

from sqlalchemy import case

from fitminiapp_api.models.program import UserProgram, UserWorkout
from fitminiapp_api.models.workout_history_import import ImportedWorkout


def workout_owner_id():
    return case(
        (UserWorkout.user_program_id.is_(None), ImportedWorkout.owner_user_id),
        else_=UserProgram.user_id,
    )
