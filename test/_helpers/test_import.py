"""Smoke test proving ``test/_helpers/`` is importable from the repo root.

The package's importability depends on ``pythonpath = ["test"]`` in
``pyproject.toml``'s ``[tool.pytest.ini_options]``. This test asserts the
canonical helper import resolves and the real-construction fixture is
callable — the foundation the test suite builds on. If ``pythonpath`` is
ever dropped or the ``_helpers`` package is moved, this test fails at
collection-resolution time rather than silently breaking every test file
that imports ``make_controller``.
"""


def test_helpers_importable() -> None:
    from _helpers.controller_fixture import make_controller

    assert callable(make_controller)
