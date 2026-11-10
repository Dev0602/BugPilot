import os

from dotenv import load_dotenv


# Load local environment configuration before reading BugPilot settings.
load_dotenv()


def _env_int(
    name,
    default,
    minimum=1,
):
    raw_value = os.getenv(
        name,
        str(default),
    )

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be an integer, "
            f"got {raw_value!r}."
        ) from exc

    if value < minimum:
        raise ValueError(
            f"{name} must be >= {minimum}, "
            f"got {value}."
        )

    return value


def _env_float(
    name,
    default,
    minimum=0.0,
):
    raw_value = os.getenv(
        name,
        str(default),
    )

    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be a number, "
            f"got {raw_value!r}."
        ) from exc

    if value < minimum:
        raise ValueError(
            f"{name} must be >= {minimum}, "
            f"got {value}."
        )

    return value


MODEL = os.getenv(
    "BUGPILOT_MODEL",
    "claude-haiku-4-5",
)

DB_PATH = os.getenv(
    "BUGPILOT_DB_PATH",
    "bugpilot.db",
)

INPUT_COST_PER_M = _env_float(
    "BUGPILOT_INPUT_COST_PER_M",
    1.0,
)

OUTPUT_COST_PER_M = _env_float(
    "BUGPILOT_OUTPUT_COST_PER_M",
    5.0,
)

MAX_ATTEMPTS = _env_int(
    "BUGPILOT_MAX_ATTEMPTS",
    3,
)

TEST_TIMEOUT_SEC = _env_int(
    "BUGPILOT_TEST_TIMEOUT_SEC",
    60,
)

DEPENDENCY_INSTALL_TIMEOUT_SEC = _env_int(
    "BUGPILOT_DEPENDENCY_INSTALL_TIMEOUT_SEC",
    180,
)
