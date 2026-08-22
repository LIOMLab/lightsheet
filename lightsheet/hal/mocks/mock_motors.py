"""Standalone mock Motors HAL for demo mode (D-08).

``MockMotors`` (container) + ``MockMotor`` (per-axis) implement ``IMotors`` /
``IMotor`` from scratch — fully decoupled from the real ``Motors`` /
``ZaberMotor`` class internals so real-class refactors cannot break the
mock (D-08). The mock tracks per-axis position in software (no serial I/O).

**Travel-limit enforcement is preserved (AGENTS.md §2 — physical safety).**
``MockMotor.move_absolute_position`` and ``move_relative_position`` raise
``ValueError`` on over-travel BEFORE any state change, exactly as the real
``ZaberMotor`` does. A mock that silently accepted an over-travel target
would let the controller's safety checks atrophy under demo mode, masking
a regression that would damage hardware on the rig.

``position_to_microsteps`` truncates toward zero (``int(...)``), matching
today's effective ``ZaberMotor._motorIO`` behavior (D-18 / Pitfall 4). The
ABC-level rounding decision is finalized in Wave 4; the mock implements the
safe default now.
"""

import logging

from lightsheet.hal.interfaces import IMotor, IMotors

logger = logging.getLogger(__name__)


class MockMotor(IMotor):
    """Mock per-axis Zaber stage for demo mode — implements IMotor with no
    serial I/O.

    Tracks ``self.position`` in software (microsteps). Travel-limit
    enforcement matches the real ``ZaberMotor``: ``move_absolute_position``
    and ``move_relative_position`` raise ``ValueError`` on over-travel
    BEFORE any state change (AGENTS.md §2).
    """

    # Class-level defaults provide pre-__init__ synthetic values (the ABC
    # now declares these as annotations, so the override is no longer
    # required for ABC satisfaction, but the defaults are kept so the mock
    # has sensible values before open() runs). __init__ sets the real
    # synthetic values as instance attributes.
    position: float = 0.0
    limit_low_microsteps: int = 0
    limit_high_microsteps: int = 0
    microstep_size: float = 0.0
    device_number: int = 0

    def __init__(
        self,
        device_number: int,
        microstep_size: float,
        limit_low_microsteps: int,
        limit_high_microsteps: int,
    ) -> None:
        # HAL error surface (AGENTS.md §10) — cleared on construct.
        self.error = 0
        self.error_message = ""

        self.device_number = device_number
        self.microstep_size = microstep_size
        self.limit_low_microsteps = limit_low_microsteps
        self.limit_high_microsteps = limit_high_microsteps
        self.origin_microsteps = 0
        self.units = "mm"
        self.inverted = False
        self.homed = False
        self.id = 0
        self.name = "MockMotor"
        self.is_supported = True

        # Software-tracked position (microsteps). Starts at the low limit.
        self.position_microsteps: int = limit_low_microsteps
        # The controller-read `position` attribute is in microsteps here;
        # callers that want units use get_position(units).
        self.position: float = float(self.position_microsteps)

    # ------------------------------------------------------------------ #
    # Motion verbs — travel-limit enforcement (AGENTS.md §2).
    # ------------------------------------------------------------------ #

    def move_absolute_position(self, absolute_position: float, units: str) -> None:
        """Move to an absolute position. Raises ``ValueError`` on over-travel
        BEFORE any state change (AGENTS.md §2 — physical safety preserved
        through the mock refactor)."""
        target_microsteps = self.position_to_microsteps(absolute_position, units)
        if target_microsteps < self.limit_low_microsteps:
            raise ValueError(
                f"Target position {absolute_position} {units}"
                " is below the low travel limit"
            )
        if target_microsteps > self.limit_high_microsteps:
            raise ValueError(
                f"Target position {absolute_position} {units}"
                " exceeds the high travel limit"
            )
        self.position_microsteps = target_microsteps
        self.position = float(target_microsteps)
        return None

    def move_relative_position(self, relative_position: float, units: str) -> None:
        """Move by a relative delta. The RESULTING position (current + delta)
        is validated against the travel limits BEFORE the move is applied.
        Raises ``ValueError`` on over-travel (AGENTS.md §2)."""
        delta_microsteps = self.position_to_microsteps(relative_position, units)
        resulting_microsteps = self.position_microsteps + delta_microsteps
        if resulting_microsteps < self.limit_low_microsteps:
            raise ValueError(
                f"Relative move would result in {resulting_microsteps} microsteps, "
                f"below the low travel limit of {self.limit_low_microsteps}"
            )
        if resulting_microsteps > self.limit_high_microsteps:
            raise ValueError(
                f"Relative move would result in {resulting_microsteps} microsteps, "
                f"exceeding the high travel limit of {self.limit_high_microsteps}"
            )
        self.position_microsteps = resulting_microsteps
        self.position = float(resulting_microsteps)
        return None

    # ------------------------------------------------------------------ #
    # Unit conversion (D-18 / Pitfall 4 — truncation toward zero).
    # ------------------------------------------------------------------ #

    def position_to_microsteps(self, position: float, units: str = "mm") -> int:
        """Convert a position to microsteps. Truncates toward zero (``int``),
        matching the effective ``ZaberMotor._motorIO`` behavior today
        (D-18 / Pitfall 4). The ABC-level rounding decision is finalized in
        Wave 4; the mock implements the safe default now."""
        if units == "m":
            factor = 1
        elif units == "cm":
            factor = pow(10, -2)
        elif units == "mm":
            factor = pow(10, -3)
        elif units == "\u03bcm":
            factor = pow(10, -6)
        elif units == "\u03bcStep":
            factor = self.microstep_size * pow(10, -6)
        else:
            factor = 0

        if self.microstep_size > 0 and factor > 0:
            microsteps = position * factor / (self.microstep_size * pow(10, -6))
        else:
            microsteps = 0
        return int(microsteps)

    def microsteps_to_position(self, microsteps: int, units: str = "mm") -> float:
        if units == "m":
            factor = 1
        elif units == "cm":
            factor = pow(10, -2)
        elif units == "mm":
            factor = pow(10, -3)
        elif units == "\u03bcm":
            factor = pow(10, -6)
        elif units == "\u03bcStep":
            factor = self.microstep_size * pow(10, -6)
        else:
            factor = 0

        if self.microstep_size > 0 and factor > 0:
            position = microsteps * self.microstep_size * pow(10, -6) / factor
        else:
            position = 0
        return position

    # ------------------------------------------------------------------ #
    # Extended surface (IMotor) — getters / setters.
    # ------------------------------------------------------------------ #

    def get_position(self, units: str) -> float:
        return self.microsteps_to_position(self.position_microsteps, units)

    def get_name(self) -> str:
        return self.name

    def set_units(self, units: str) -> None:
        self.units = units
        return None

    def set_inverted(self, inverted: bool) -> None:
        self.inverted = inverted
        return None

    def set_limit_low(self, position: float, units: str) -> None:
        self.limit_low_microsteps = self.position_to_microsteps(position, units)
        return None

    def set_limit_high(self, position: float, units: str) -> None:
        self.limit_high_microsteps = self.position_to_microsteps(position, units)
        return None

    def set_origin(self, position: float, units: str) -> None:
        self.origin_microsteps = self.position_to_microsteps(position, units)
        return None

    # ------------------------------------------------------------------ #
    # Controller-called getters (IMotorCore) — the 3 getters the
    # controller's updateUi_units/updateUi_check_positions/updateUi_set_origin
    # call graph reads (46 call sites). Mirror ZaberMotor.get_limit_low/
    # get_limit_high/get_origin (real/motors.py:317-329).
    # ------------------------------------------------------------------ #

    def get_limit_low(self, units: str) -> float:
        return self.microsteps_to_position(self.limit_low_microsteps, units)

    def get_limit_high(self, units: str) -> float:
        return self.microsteps_to_position(self.limit_high_microsteps, units)

    def get_origin(self, units: str) -> float:
        return self.microsteps_to_position(self.origin_microsteps, units)

    # ------------------------------------------------------------------ #
    # Extended surface (IMotor) — getters + lifecycle extras not
    # GUI-wired. Mirror ZaberMotor.get_units/get_inverted/ask_id/move_home.
    # ------------------------------------------------------------------ #

    def get_units(self) -> str:
        return self.units

    def get_inverted(self) -> bool:
        return self.inverted

    def ask_id(self) -> int:
        # Mock has no serial hardware; self.id stays 0 set in __init__.
        # The mock is always "supported" so no hardware probe is needed.
        return self.id

    def move_home(self) -> None:
        # Mock has no physical home; no-op per the mock lifecycle pattern.
        return None


class MockMotors(IMotors):
    """Mock Motors container for demo mode — implements IMotors with no
    serial I/O.

    Constructs three ``MockMotor`` instances for the vertical / horizontal /
    camera axes, mirroring the real ``Motors`` container's attribute names
    (``vertical`` / ``horizontal`` / ``camera``). The per-axis motors carry
    the same travel-limit surface as the real ``ZaberMotor`` so the
    controller's safety checks exercise the same code path under demo.
    """

    # Class-level defaults provide pre-__init__ synthetic values (the ABC
    # now declares these as annotations, so the override is no longer
    # required for ABC satisfaction, but the defaults are kept so the mock
    # has sensible values before __init__ runs). __init__ sets the real
    # instances as instance attributes.
    vertical: IMotor | None = None
    horizontal: IMotor | None = None
    camera: IMotor | None = None

    def __init__(self) -> None:
        # HAL error surface (AGENTS.md §10) — cleared on construct.
        self.error = 0
        self.error_message = ""

        # Construct the three per-axis motors with synthetic defaults
        # mirroring the real Zaber T-LS stage families. Travel limits match
        # the config.ini defaults (Motors section): vertical/horizontal
        # 0..10 mm, camera 0..50 mm.
        # T-LSM050A (vertical): microstep_size 0.047625 µm, 1066666 microsteps max.
        self.vertical = MockMotor(
            device_number=1,
            microstep_size=0.047625,
            limit_low_microsteps=0,
            limit_high_microsteps=1066666,
        )
        # T-LSM100B (horizontal): microstep_size 0.19050 µm, 533333 microsteps max.
        self.horizontal = MockMotor(
            device_number=2,
            microstep_size=0.19050,
            limit_low_microsteps=0,
            limit_high_microsteps=533333,
        )
        # T-LSR150B (camera): microstep_size 0.49609 µm, 258015 microsteps max.
        self.camera = MockMotor(
            device_number=3,
            microstep_size=0.49609,
            limit_low_microsteps=0,
            limit_high_microsteps=258015,
        )

    # ------------------------------------------------------------------ #
    # Lifecycle verbs — no-ops ending with ``return None`` (AGENTS.md §10).
    # ------------------------------------------------------------------ #

    def open(self) -> None:
        return None

    def close(self) -> None:
        return None

    # ------------------------------------------------------------------ #
    # Extended surface (IMotors).
    # ------------------------------------------------------------------ #

    def get_properties(self) -> dict[str, str]:
        return {
            "vertical name": self.vertical.get_name(),
            "horizontal name": self.horizontal.get_name(),
            "camera name": self.camera.get_name(),
        }

    def get_positions(self) -> dict[str, float]:
        return {
            "vertical position": self.vertical.get_position("mm"),
            "horizontal position": self.horizontal.get_position("mm"),
            "camera position": self.camera.get_position("mm"),
        }

    # ------------------------------------------------------------------ #
    # Extended config surface (IMotors) — no-op stubs. The mock has no
    # config.ini to read or persist; the synthetic defaults are already
    # set in __init__.
    # ------------------------------------------------------------------ #

    def cfg_load_ini(self) -> None:
        return None

    def cfg_save_ini(self) -> None:
        return None
