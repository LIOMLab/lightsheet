"""Standalone mock ETLs HAL for demo mode (D-08, D-06).

``MockETLs`` (container) + ``MockOptotune`` (per-lens) implement ``IETLs`` /
``IOptotune`` from scratch — fully decoupled from the real ``ETLs`` /
``Optotune`` class internals so real-class refactors cannot break the mock
(D-08). The container's lifecycle verbs (``open`` / ``close`` /
``set_analog_mode``) are no-ops returning ``None`` (AGENTS.md §10) so the
controller's ``self.etls.open(); self.etls.set_analog_mode()`` call sites
are unchanged between real and demo runs.

``MockOptutune``'s ~30 CRC-protected serial commands raise
``NotImplementedError`` (D-06). They cannot be verified against real
hardware on the Mac dev box; rig-verification task HW2-01 covers them. A
mock that silently succeeded would mask a real-device protocol regression,
so the stubs raise rather than return a fake value.
"""

import logging

from lightsheet.hal.interfaces import IETLs, IOptotune

logger = logging.getLogger(__name__)


class MockOptotune(IOptotune):
    """Mock per-lens Optotune EL-10-30 for demo mode — implements IOptotune.

    The ~30 CRC-protected serial commands raise ``NotImplementedError``
    (D-06) because the CRC protocol cannot be verified against real
    hardware on the Mac dev box. Rig-verification task HW2-01 covers them.
    A mock that silently succeeded would mask a real-device protocol
    regression, so the stubs raise rather than return a fake value.
    """

    def __init__(self, port: str | None = None) -> None:
        self.port = port
        # HAL error surface (AGENTS.md §10) — cleared on construct.
        self.error = 0
        self.error_message = ""

    def _not_implemented(self, name: str, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(
            f"MockOptotune.{name}() is not implemented — the CRC-protected "
            "serial protocol cannot be verified against real hardware on the "
            "Mac dev box (D-06). Rig-verification task HW2-01 covers it."
        )

    # ------------------------------------------------------------------ #
    # IOptotune surface — all raise NotImplementedError (D-06).
    # ------------------------------------------------------------------ #

    def connect(self) -> None:
        # connect() is called by MockETLs.open() indirectly; treat it as a
        # no-op so the container's open() flow runs under demo. The real
        # Optotune.connect() opens the serial port and handshakes; the mock
        # has no serial port, so it just records that it was called.
        return None

    def close(self, soft_close: bool | None = None) -> None:
        return None

    def handshake(self) -> bytes:
        # handshake() is called by MockETLs.close(); return the ready
        # sentinel so the container's close() flow runs under demo.
        return b"Ready\r\n"

    def firmwaretype(self) -> int:
        self._not_implemented("firmwaretype")

    def firmwarebranch(self) -> int:
        self._not_implemented("firmwarebranch")

    def partnumber(self) -> bytes:
        self._not_implemented("partnumber")

    def current_upper(self, value: float | None = None) -> float:
        self._not_implemented("current_upper", value)

    def current_lower(self, value: float | None = None) -> float:
        self._not_implemented("current_lower", value)

    def firmwareversion(self) -> str:
        self._not_implemented("firmwareversion")

    def deviceid(self) -> bytes:
        self._not_implemented("deviceid")

    def gain(self, value: float | None = None) -> float | tuple[int, float, float]:
        self._not_implemented("gain", value)

    def serialnumber(self) -> bytes:
        self._not_implemented("serialnumber")

    def current(self, value: float | None = None) -> float:
        self._not_implemented("current", value)

    def siggen_upper(self, value: float | None = None) -> float:
        self._not_implemented("siggen_upper", value)

    def siggen_lower(self, value: float | None = None) -> float:
        self._not_implemented("siggen_lower", value)

    def siggen_freq(self, value: float | None = None) -> float:
        self._not_implemented("siggen_freq", value)

    def temp_limits(
        self, value: tuple[float, float] | None = None
    ) -> tuple[float, float]:
        self._not_implemented("temp_limits", value)

    def focalpower(self, value: float | None = None) -> float:
        self._not_implemented("focalpower", value)

    def current_max(self, value: float | None = None) -> float:
        self._not_implemented("current_max", value)

    def temp_reading(self) -> float:
        self._not_implemented("temp_reading")

    def get_status(self) -> bytes:
        self._not_implemented("get_status")

    def eeprom_read(self, value: int) -> int:
        self._not_implemented("eeprom_read", value)

    def analog_input(self) -> int:
        self._not_implemented("analog_input")

    def eeprom_write(self, address: int, value: int) -> int:
        self._not_implemented("eeprom_write", address, value)

    def eeprom_contents(self) -> bytes:
        self._not_implemented("eeprom_contents")

    def mode(self, mode_str: str | None = None) -> str:
        # mode() is called by MockETLs.set_analog_mode(); treat the
        # "analog" set case as a no-op so the container's flow runs under
        # demo. Get-case (mode_str is None) raises NotImplementedError.
        if mode_str is not None:
            return mode_str
        self._not_implemented("mode", mode_str)


class MockETLs(IETLs):
    """Mock ETLs container for demo mode — implements IETLs with no serial
    I/O.

    Constructs two ``MockOptotune`` instances (left / right) mirroring the
    real ``ETLs`` container's ``etl_left`` / ``etl_right`` attributes. The
    lifecycle verbs (``open`` / ``close`` / ``set_analog_mode``) are no-ops
    returning ``None`` (AGENTS.md §10).
    """

    def __init__(self) -> None:
        # HAL error surface (AGENTS.md §10) — cleared on construct.
        self.error = 0
        self.error_message = ""

        self.etl_left = MockOptotune(port="COM5")
        self.etl_right = MockOptotune(port="COM6")

    # ------------------------------------------------------------------ #
    # Lifecycle verbs — no-ops ending with ``return None`` (AGENTS.md §10).
    # ------------------------------------------------------------------ #

    def open(self) -> None:
        # The real ETLs.open() constructs Optotune per lens and calls
        # connect(); the mock's MockOptutune.connect() is a no-op, so just
        # leave the per-lens instances in place.
        return None

    def close(self) -> None:
        return None

    def set_analog_mode(self) -> None:
        # The real ETLs.set_analog_mode() calls etl.mode("analog") on each
        # lens; the mock's MockOptutune.mode("analog") is a no-op.
        if self.etl_left is not None:
            self.etl_left.mode("analog")
        if self.etl_right is not None:
            self.etl_right.mode("analog")
        return None

    # ------------------------------------------------------------------ #
    # Extended surface (IETLs).
    # ------------------------------------------------------------------ #

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
