"""Standalone mock ETLs HAL for demo mode.

``MockETLs`` (container) + ``MockOptotune`` (per-lens) implement ``IETLs`` /
``IOptotune`` with no serial I/O. The ~30 CRC-protected serial commands raise
``NotImplementedError`` — they cannot be verified against real hardware on
the dev box, and silently succeeding would mask a protocol regression.
"""

import logging

from lightsheet.hal.interfaces import IETLs, IOptotune

logger = logging.getLogger(__name__)


class MockOptotune(IOptotune):
    """Mock per-lens Optotune EL-10-30 for demo mode — implements IOptotune.

    CRC-protected serial commands raise ``NotImplementedError`` because the
    protocol cannot be verified against real hardware on the dev box.
    """

    def __init__(self, port: str | None = None) -> None:
        self.port = port
        self.error = 0
        self.error_message = ""

    def _not_implemented(self, name: str, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(
            f"MockOptotune.{name}() is not implemented — the CRC-protected "
            "serial protocol cannot be verified against real hardware on the "
            "Mac dev box."
        )

    def connect(self) -> None:
        # No-op so the container's open() flow runs under demo.
        return None

    def close(self, soft_close: bool | None = None) -> None:
        return None

    def handshake(self) -> bytes:
        # Return the ready sentinel so the container's close() flow runs under demo.
        return b"Ready\r\n"

    def firmwaretype(self) -> int:  # ty: ignore[invalid-return-type]
        self._not_implemented("firmwaretype")

    def firmwarebranch(self) -> int:  # ty: ignore[invalid-return-type]
        self._not_implemented("firmwarebranch")

    def partnumber(self) -> bytes:  # ty: ignore[invalid-return-type]
        self._not_implemented("partnumber")

    def current_upper(self, value: float | None = None) -> float:  # ty: ignore[invalid-return-type]
        self._not_implemented("current_upper", value)

    def current_lower(self, value: float | None = None) -> float:  # ty: ignore[invalid-return-type]
        self._not_implemented("current_lower", value)

    def firmwareversion(self) -> str:  # ty: ignore[invalid-return-type]
        self._not_implemented("firmwareversion")

    def deviceid(self) -> bytes:  # ty: ignore[invalid-return-type]
        self._not_implemented("deviceid")

    def gain(self, value: float | None = None) -> float | tuple[int, float, float]:  # ty: ignore[invalid-return-type]
        self._not_implemented("gain", value)

    def serialnumber(self) -> bytes:  # ty: ignore[invalid-return-type]
        self._not_implemented("serialnumber")

    def current(self, value: float | None = None) -> float:  # ty: ignore[invalid-return-type]
        self._not_implemented("current", value)

    def siggen_upper(self, value: float | None = None) -> float:  # ty: ignore[invalid-return-type]
        self._not_implemented("siggen_upper", value)

    def siggen_lower(self, value: float | None = None) -> float:  # ty: ignore[invalid-return-type]
        self._not_implemented("siggen_lower", value)

    def siggen_freq(self, value: float | None = None) -> float:  # ty: ignore[invalid-return-type]
        self._not_implemented("siggen_freq", value)

    def temp_limits(
        self, value: tuple[float, float] | None = None
    ) -> tuple[float, float]:  # ty: ignore[invalid-return-type]
        self._not_implemented("temp_limits", value)

    def focalpower(self, value: float | None = None) -> float:  # ty: ignore[invalid-return-type]
        self._not_implemented("focalpower", value)

    def current_max(self, value: float | None = None) -> float:  # ty: ignore[invalid-return-type]
        self._not_implemented("current_max", value)

    def temp_reading(self) -> float:  # ty: ignore[invalid-return-type]
        self._not_implemented("temp_reading")

    def get_status(self) -> bytes:  # ty: ignore[invalid-return-type]
        self._not_implemented("get_status")

    def eeprom_read(self, value: int) -> int:  # ty: ignore[invalid-return-type]
        self._not_implemented("eeprom_read", value)

    def analog_input(self) -> int:  # ty: ignore[invalid-return-type]
        self._not_implemented("analog_input")

    def eeprom_write(self, address: int, value: int) -> int:  # ty: ignore[invalid-return-type]
        self._not_implemented("eeprom_write", address, value)

    def eeprom_contents(self) -> bytes:  # ty: ignore[invalid-return-type]
        self._not_implemented("eeprom_contents")

    def mode(self, mode_str: str | None = None) -> str:  # ty: ignore[invalid-return-type]
        # "analog" set case is a no-op so the container's flow runs under demo.
        # Get-case (mode_str is None) raises NotImplementedError.
        if mode_str is not None:
            return mode_str
        self._not_implemented("mode", mode_str)


class MockETLs(IETLs):
    """Mock ETLs container for demo mode — implements IETLs with no serial I/O."""

    def __init__(self) -> None:
        self.error = 0
        self.error_message = ""

        self.etl_left = MockOptotune(port="COM5")
        self.etl_right = MockOptotune(port="COM6")

    def open(self) -> None:
        return None

    def close(self) -> None:
        return None

    def set_analog_mode(self) -> None:
        if self.etl_left is not None:
            self.etl_left.mode("analog")
        if self.etl_right is not None:
            self.etl_right.mode("analog")
        return None

    def set_current_mode(self) -> None:
        if self.etl_left is not None:
            self.etl_left.mode("current")
        if self.etl_right is not None:
            self.etl_right.mode("current")
        return None

    def get_mode(self) -> None:
        return None

    def get_temperature(self) -> None:
        return None
