"""Contract tests for the TST-04 conformance suite infrastructure.

These tests verify the ``ConformanceContract`` dataclass shape, the 6
per-device contract constants, and the ``has_hardware`` fixture / module-level
gate that the parametrized conformance tests rely on. They are the RED phase
for Plan 03-05 Task 1: the test fails because ``lightsheet/hal/conformance.py``
does not exist yet; GREEN is the contract module + conftest fixture landing.

The 6 parametrized ``test/test_<device>_conformance.py`` files (Task 2)
consume these constants via ``from lightsheet.hal.conformance import
CAMERA_CONTRACT`` etc. and run one assertion body behind both ``[real, mock]``.
"""

import os

import pytest


def test_conformance_contract_is_dataclass_with_required_fields() -> None:
    """ConformanceContract must be a dataclass with lifecycle_methods,
    read_attrs, and setter_methods fields (D-15)."""
    from dataclasses import is_dataclass

    from lightsheet.hal.conformance import ConformanceContract

    assert is_dataclass(ConformanceContract)
    # The three fields the parametrize fixture consumes.
    fields = {f.name for f in __import__("dataclasses").fields(ConformanceContract)}
    assert "lifecycle_methods" in fields
    assert "read_attrs" in fields
    assert "setter_methods" in fields


def test_conformance_contract_has_assert_methods() -> None:
    """ConformanceContract must expose assert_lifecycle / assert_error_surface
    / assert_read_attrs methods — the single assertion body the parametrized
    conformance tests call behind both [real, mock] (D-15)."""
    from lightsheet.hal.conformance import ConformanceContract

    assert callable(getattr(ConformanceContract, "assert_lifecycle", None))
    assert callable(getattr(ConformanceContract, "assert_error_surface", None))
    assert callable(getattr(ConformanceContract, "assert_read_attrs", None))


@pytest.mark.parametrize(
    "contract_name",
    [
        "CAMERA_CONTRACT",
        "SIGGEN_CONTRACT",
        "MOTORS_CONTRACT",
        "LASERS_CONTRACT",
        "ETLS_CONTRACT",
        "IBEAM_CONTRACT",
    ],
)
def test_per_device_contract_constant_exists(contract_name: str) -> None:
    """Each per-device contract constant is a ConformanceContract instance
    (D-15 — derived from the core ABC, one per device family)."""
    from lightsheet.hal.conformance import ConformanceContract

    mod = __import__("lightsheet.hal.conformance", fromlist=[contract_name])
    contract = getattr(mod, contract_name)
    assert isinstance(contract, ConformanceContract), (
        f"{contract_name} must be a ConformanceContract instance"
    )


def test_has_hardware_module_level_bool_exists() -> None:
    """conftest exposes a module-level ``_has_hardware`` bool for use in
    ``pytest.param(marks=skipif(not _has_hardware))`` at collection time
    (parametrize marks are evaluated at collection, not at fixture-resolution
    time, so the module-level bool is needed)."""
    import sys

    # conftest is not importable as a top-level package under xdist's
    # importlib mode; reach it via the test/ directory on sys.path. The
    # module is already loaded by pytest's conftest collection mechanism,
    # so this resolves to the same in-memory module.
    test_dir = os.path.dirname(os.path.abspath(__file__))
    if test_dir not in sys.path:
        sys.path.insert(0, test_dir)
    import conftest

    assert hasattr(conftest, "_has_hardware")
    assert isinstance(conftest._has_hardware, bool)


def test_has_hardware_fixture_returns_env_value(has_hardware: bool) -> None:
    """The ``has_hardware`` session fixture returns a bool matching the
    LIGHTSHEET_HW env var (False on Mac default, True on rig when
    LIGHTSHEET_HW=1). This test runs under the default (unset) env, so the
    fixture must return False here; the rig sets LIGHTSHEET_HW=1 and the
    fixture returns True there."""
    assert isinstance(has_hardware, bool)
    # Mac dev box default: LIGHTSHEET_HW unset → False.
    assert has_hardware is False, (
        "has_hardware fixture must return False when LIGHTSHEET_HW is unset "
        "(Mac default); the rig sets LIGHTSHEET_HW=1"
    )
