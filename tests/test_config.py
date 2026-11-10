import importlib

import pytest

from backend.app import config


def reload_config(
    monkeypatch,
    **environment,
):
    names = [
        "BUGPILOT_MODEL",
        "BUGPILOT_DB_PATH",
        "BUGPILOT_INPUT_COST_PER_M",
        "BUGPILOT_OUTPUT_COST_PER_M",
        "BUGPILOT_MAX_ATTEMPTS",
        "BUGPILOT_TEST_TIMEOUT_SEC",
        "BUGPILOT_DEPENDENCY_INSTALL_TIMEOUT_SEC",
    ]

    for name in names:
        monkeypatch.delenv(
            name,
            raising=False,
        )

    for name, value in environment.items():
        monkeypatch.setenv(
            name,
            str(value),
        )

    return importlib.reload(
        config
    )


def test_default_configuration(
    monkeypatch,
):
    cfg = reload_config(
        monkeypatch
    )

    assert (
        cfg.MODEL
        == "claude-haiku-4-5"
    )

    assert (
        cfg.DB_PATH
        == "bugpilot.db"
    )

    assert (
        cfg.INPUT_COST_PER_M
        == 1.0
    )

    assert (
        cfg.OUTPUT_COST_PER_M
        == 5.0
    )

    assert (
        cfg.MAX_ATTEMPTS
        == 3
    )

    assert (
        cfg.TEST_TIMEOUT_SEC
        == 60
    )

    assert (
        cfg.DEPENDENCY_INSTALL_TIMEOUT_SEC
        == 180
    )


def test_environment_overrides(
    monkeypatch,
):
    cfg = reload_config(
        monkeypatch,
        BUGPILOT_MODEL="test-model",
        BUGPILOT_DB_PATH="test.db",
        BUGPILOT_INPUT_COST_PER_M="2.5",
        BUGPILOT_OUTPUT_COST_PER_M="7.5",
        BUGPILOT_MAX_ATTEMPTS="5",
        BUGPILOT_TEST_TIMEOUT_SEC="75",
        BUGPILOT_DEPENDENCY_INSTALL_TIMEOUT_SEC="240",
    )

    assert (
        cfg.MODEL
        == "test-model"
    )

    assert (
        cfg.DB_PATH
        == "test.db"
    )

    assert (
        cfg.INPUT_COST_PER_M
        == 2.5
    )

    assert (
        cfg.OUTPUT_COST_PER_M
        == 7.5
    )

    assert (
        cfg.MAX_ATTEMPTS
        == 5
    )

    assert (
        cfg.TEST_TIMEOUT_SEC
        == 75
    )

    assert (
        cfg.DEPENDENCY_INSTALL_TIMEOUT_SEC
        == 240
    )


@pytest.mark.parametrize(
    "name,value",
    [
        (
            "BUGPILOT_MAX_ATTEMPTS",
            "zero",
        ),
        (
            "BUGPILOT_TEST_TIMEOUT_SEC",
            "abc",
        ),
        (
            "BUGPILOT_DEPENDENCY_INSTALL_TIMEOUT_SEC",
            "1.5",
        ),
    ],
)
def test_invalid_integer_configuration(
    monkeypatch,
    name,
    value,
):
    monkeypatch.setenv(
        name,
        value,
    )

    with pytest.raises(
        ValueError
    ):
        importlib.reload(
            config
        )


@pytest.mark.parametrize(
    "name,value",
    [
        (
            "BUGPILOT_MAX_ATTEMPTS",
            "0",
        ),
        (
            "BUGPILOT_TEST_TIMEOUT_SEC",
            "0",
        ),
        (
            "BUGPILOT_DEPENDENCY_INSTALL_TIMEOUT_SEC",
            "-1",
        ),
    ],
)
def test_integer_minimum_validation(
    monkeypatch,
    name,
    value,
):
    monkeypatch.setenv(
        name,
        value,
    )

    with pytest.raises(
        ValueError
    ):
        importlib.reload(
            config
        )