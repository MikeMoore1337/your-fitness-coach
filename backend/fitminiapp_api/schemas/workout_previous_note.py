from datetime import date

from pydantic import BaseModel


class PreviousWorkoutNote(BaseModel):
    note: str
    completed_on: date
    day_number: int
    workout_title: str
    is_latest_completion: bool


class PreviousWorkoutNoteResponse(BaseModel):
    previous_note: PreviousWorkoutNote | None = None
