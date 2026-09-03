"""Mock-serial ETLs open-failure branch.

Exercises ``lightsheet.hal.real.etls.ETLs.open()`` when one side's
``Optotune`` constructor/connect raises a transport exception. The real
HAL catches only ``SerialException``/``OSError``/``RuntimeError``, sets the
HAL error surface, and leaves the failed lens as ``None`` while still
opening the other side.

These are pure-logic behavior tests — no serial hardware required.
"""

from unittest.mock import MagicMock, patch

import lightsheet.hal.real.etls as etls_mod


def test_etls_open_left_failure_continues_to_right() -> None:
    """Left ETL open failure sets etl_left=None and the error surface,
    but open() still attempts and succeeds on the right side."""
    etls = etls_mod.ETLs(port_etl_left="COM5", port_etl_right="COM6")
    fake_right = MagicMock()

    with patch.object(
        etls_mod,
        "Optotune",
        side_effect=[etls_mod.serial.SerialException("no left device"), fake_right],
    ):
        etls.open()

    assert etls.etl_left is None
    assert etls.etl_right is fake_right
    assert etls.error == 1
    assert "Left ETL open failed" in etls.error_message


def test_etls_open_right_failure_keeps_left_opened() -> None:
    """Right ETL open failure leaves the already-opened left lens intact
    and records the right-side error."""
    etls = etls_mod.ETLs(port_etl_left="COM5", port_etl_right="COM6")
    fake_left = MagicMock()

    with patch.object(
        etls_mod,
        "Optotune",
        side_effect=[fake_left, etls_mod.serial.SerialException("no right device")],
    ):
        etls.open()

    assert etls.etl_left is fake_left
    assert etls.etl_right is None
    assert etls.error == 1
    assert "Right ETL open failed" in etls.error_message
