class ProgramError(ValueError):
    """Domain validation error returned by program and coaching workflows."""


ASSIGNMENT_CONFLICT_ERRORS = {
    "Active program replacement requires confirmation",
    "Cannot replace a program while a workout is in progress",
}

ASSIGNMENT_VALIDATION_PREFIXES = (
    "Program duration must",
    "A weekly program supports",
    "Program is too large",
    "This periodized template is available",
    "Choose one weekday",
    "Weekdays must",
    "Program weekdays must",
    "Program start date cannot",
)


def assignment_error_status(detail: str) -> int:
    if detail in ASSIGNMENT_CONFLICT_ERRORS:
        return 409
    if detail.startswith(ASSIGNMENT_VALIDATION_PREFIXES):
        return 422
    return 400
