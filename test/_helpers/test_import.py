"""Smoke test proving ``test/_helpers/`` is importable from the repo root.

The package's importability depends on ``pythonpath = ["test"]`` in
``pyproject.toml``'s ``[tool.pytest.ini_options]`` (landed in plan 05.1-01).
This test asserts the canonical helper imports resolve and the promoted
factories are callable — the foundation the test-writing-to-green plans
(05.1-04/05/06) build on. If ``pythonpath`` is ever dropped or the
``_helpers`` package is moved, this test fails at collection-resolution
time rather than silently breaking every repointed test file.
"""


def test_helpers_importable() -> None:
    from _helpers import controller, factories, contracts

    assert callable(controller._load_method)
    assert callable(controller._slice_method)
    assert callable(factories._make_motor)
    assert callable(factories._make_daq_l1)
    assert callable(factories._make_mock_l1)
    assert callable(factories._make_ibeam_smart_l2)
    assert callable(factories._make_mock_l2)
    assert callable(factories._make_write_laser)
    assert hasattr(contracts, "DeviceConformanceBase")
