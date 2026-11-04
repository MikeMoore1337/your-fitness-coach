"""File adapters for completed workout history."""

from fitminiapp_api.services.workout_history_adapters import fitnotes, hevy, strong

ADAPTERS = {"hevy": hevy.parse, "strong": strong.parse, "fitnotes": fitnotes.parse}
