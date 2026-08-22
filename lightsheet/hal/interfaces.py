"""HAL interface ABCs for the lightsheet microscope device families.

The Phase 3 architecture (D-01) splits each hardware device family into
three concerns: this module (the abstract interfaces), ``lightsheet/hal/real/``
(the vendor-bound concrete implementations), and ``lightsheet/hal/mocks/``
(standalone mock implementations used under ``--demo`` / ``LIGHTSHEET_DEMO=1``).

Layered ABCs (D-04):
- ``ICameraCore`` is the **core** ABC — the controller-reachable surface.
  The boundary is pinned to the controller's actual call graph (D-05): the
  methods/attributes ``lightsheet/gui/controller.py`` invokes or reads on a
  camera instance. The controller reads HAL state as *direct attributes*
  (``camera.xsize``, ``camera.exposure_time``), not via ``get_*`` methods, so
  those attributes are declared here as ``@property`` + ``@abstractmethod``
  slots. Phase 5 dependency-injection seams type-hint against the core ABC.
- ``ICamera`` is the **extended** ABC — the full public method surface of
  the concrete ``Camera`` class. Mocks implement the extended ABC; the
  TST-04 conformance parametrization runs the same assertions behind both
  ``[real, mock]`` against this surface.

This module imports only ``abc`` — no vendor SDKs, no numpy. The ABC is a
pure-Python declarative contract; vendor and numpy imports live in
``real/`` and ``mocks/``.
"""

from abc import ABC, abstractmethod
from typing import Any


class ICameraCore(ABC):
    """Controller-reachable Camera surface (D-05: pinned to controller call graph).

    The controller (``lightsheet/gui/controller.py``) reads camera state as
    *direct attributes* — ``self.camera.xsize``, ``self.camera.ysize``,
    ``self.camera.exposure_time``, ``self.camera.shutter_mode``,
    ``self.camera.line_time``, ``self.camera.lightsheet_exposed_lines``,
    ``self.camera.lightsheet_delay_lines``, ``self.camera.recorder_timeout_status``.
    These MUST be declared as ``@property`` + ``@abstractmethod`` slots (D-04)
    so Phase 5 DI seams type-check the attribute surface, not just method
    signatures.

    The cross-cutting HAL error surface (``error`` / ``error_message``,
    AGENTS.md §10) is declared as a class-level annotation so every concrete
    Camera (real or mock) carries it.
    """

    # HAL error surface (AGENTS.md §10) — every HAL ABC declares these.
    # Concrete classes set them as instance attributes in ``__init__``.
    error: int
    error_message: str

    # Controller-read attributes (D-04) — declared as @property + @abstractmethod
    # slots because the controller reads them as direct attributes, not via
    # getters. Concrete classes implement them as plain instance attributes
    # (the @property decorator here is the ABC contract; the concrete impl
    # satisfies it by setting the attribute in __init__/open).
    @property
    @abstractmethod
    def xsize(self) -> int | None: ...

    @property
    @abstractmethod
    def ysize(self) -> int | None: ...

    @property
    @abstractmethod
    def exposure_time(self) -> float: ...

    @property
    @abstractmethod
    def shutter_mode(self) -> str: ...

    @property
    @abstractmethod
    def line_time(self) -> float | None: ...

    @property
    @abstractmethod
    def lightsheet_exposed_lines(self) -> int: ...

    @property
    @abstractmethod
    def lightsheet_delay_lines(self) -> int: ...

    @property
    @abstractmethod
    def recorder_timeout_status(self) -> bool: ...

    # Lifecycle verbs (AGENTS.md §10) — abstract methods returning None.
    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def arm(self) -> None: ...

    @abstractmethod
    def disarm(self) -> None: ...

    @abstractmethod
    def arm_scan(self) -> None: ...

    @abstractmethod
    def start_recorder(self, number_of_images: int) -> None: ...

    @abstractmethod
    def monitor_recorder(self, number_of_images: int) -> None: ...

    @abstractmethod
    def stop_recorder(self) -> None: ...

    @abstractmethod
    def delete_recorder(self) -> None: ...


class ICamera(ICameraCore):
    """Extended Camera surface — the full public method set of the concrete
    ``Camera`` class. Mocks implement this; TST-04 conformance parametrization
    runs against this surface behind both ``[real, mock]``.
    """

    @abstractmethod
    def grab_image(self, exposure_time_ms: int = 100) -> Any: ...

    @abstractmethod
    def get_camera_temperature(self) -> float | None: ...

    @abstractmethod
    def get_sensor_temperature(self) -> float | None: ...

    @abstractmethod
    def get_power_temperature(self) -> float | None: ...

    @abstractmethod
    def get_xsize(self) -> int | None: ...

    @abstractmethod
    def get_ysize(self) -> int | None: ...

    @abstractmethod
    def set_exposure_time(self, exposure_time_ms: int) -> None: ...

    @abstractmethod
    def set_shutter_mode(self, shutter_mode: str) -> None: ...

    @abstractmethod
    def copy_recorder_images(self, number_of_images: int) -> Any: ...


# =========================================================================== #
# SigGen family
# =========================================================================== #


class ISigGenCore(ABC):
    """Controller-reachable SigGen surface (D-05: pinned to controller call graph).

    The controller (``lightsheet/gui/controller.py``) reads SigGen state as
    *direct attributes* — ``self.siggen.galvo_left_amplitude``,
    ``self.siggen.galvo_right_amplitude``, ``self.siggen.galvo_left_offset``,
    ``self.siggen.galvo_right_offset``, ``self.siggen.etl_left_amplitude``,
    ``self.siggen.etl_right_amplitude``, ``self.siggen.etl_left_offset``,
    ``self.siggen.etl_right_offset``, ``self.siggen.waveform_cycles``,
    ``self.siggen.waveform_metadata``. These are declared as ``@property`` +
    ``@abstractmethod`` slots (D-04) so Phase 5 DI seams type-check the
    attribute surface.

    The cross-cutting HAL error surface (``error`` / ``error_message``,
    AGENTS.md §10) is declared as a class-level annotation.
    """

    # HAL error surface (AGENTS.md §10).
    error: int
    error_message: str

    # Controller-read attributes (D-04) — declared as @property + @abstractmethod
    # slots because the controller reads them as direct attributes, not via
    # getters. Concrete classes implement them as plain instance attributes.
    @property
    @abstractmethod
    def galvo_left_amplitude(self) -> float: ...

    @property
    @abstractmethod
    def galvo_right_amplitude(self) -> float: ...

    @property
    @abstractmethod
    def galvo_left_offset(self) -> float: ...

    @property
    @abstractmethod
    def galvo_right_offset(self) -> float: ...

    @property
    @abstractmethod
    def etl_left_amplitude(self) -> float: ...

    @property
    @abstractmethod
    def etl_right_amplitude(self) -> float: ...

    @property
    @abstractmethod
    def etl_left_offset(self) -> float: ...

    @property
    @abstractmethod
    def etl_right_offset(self) -> float: ...

    @property
    @abstractmethod
    def waveform_cycles(self) -> int | None: ...

    @property
    @abstractmethod
    def waveform_metadata(self) -> dict | None: ...

    # Lifecycle verbs (AGENTS.md §10) — abstract methods returning None.
    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def arm(self) -> None: ...

    @abstractmethod
    def disarm(self) -> None: ...

    @abstractmethod
    def compute_scan_waveforms(self) -> None: ...

    @abstractmethod
    def create_scanner(self) -> None: ...

    @abstractmethod
    def start_scanner(self) -> None: ...

    @abstractmethod
    def stop_scanner(self) -> None: ...

    @abstractmethod
    def delete_scanner(self) -> None: ...


class ISigGen(ISigGenCore):
    """Extended SigGen surface — the full public method set of the concrete
    ``SigGen`` class. Mocks implement this; the TST-04 conformance
    parametrization runs against this surface behind both ``[real, mock]``.
    """

    @abstractmethod
    def update_all(
        self, left_galvo: float, right_galvo: float, left_etl: float, right_etl: float
    ) -> None: ...

    @abstractmethod
    def update_galvos(self, left_galvo: float, right_galvo: float) -> None: ...

    @abstractmethod
    def update_etls(self, left_etl: float, right_etl: float) -> None: ...

    @abstractmethod
    def monitor_scanner(self) -> None: ...


# =========================================================================== #
# Motors family (container + per-axis)
# =========================================================================== #


class IMotorCore(ABC):
    """Controller-reachable per-axis motor surface (D-05).

    The controller reads per-axis motor state as direct attributes —
    ``motor.position``, ``motor.limit_low_microsteps``,
    ``motor.limit_high_microsteps``, ``motor.microstep_size``,
    ``motor.device_number``. These are declared as ``@property`` +
    ``@abstractmethod`` slots (D-04).

    Travel-limit enforcement (AGENTS.md §2) is a physical-safety contract:
    ``move_absolute_position`` and ``move_relative_position`` MUST raise
    ``ValueError`` on over-travel BEFORE any state change or serial command.
    Concrete classes (real ``ZaberMotor`` and ``MockMotor``) implement this.
    """

    # HAL error surface (AGENTS.md §10).
    error: int
    error_message: str

    @property
    @abstractmethod
    def position(self) -> float: ...

    @property
    @abstractmethod
    def limit_low_microsteps(self) -> int: ...

    @property
    @abstractmethod
    def limit_high_microsteps(self) -> int: ...

    @property
    @abstractmethod
    def microstep_size(self) -> float: ...

    @property
    @abstractmethod
    def device_number(self) -> int: ...

    # Lifecycle / motion verbs. move_absolute_position / move_relative_position
    # raise ValueError on over-travel (AGENTS.md §2 — physical safety).
    @abstractmethod
    def move_absolute_position(self, absolute_position: float, units: str) -> None: ...

    @abstractmethod
    def move_relative_position(self, relative_position: float, units: str) -> None: ...

    @abstractmethod
    def position_to_microsteps(self, position: float, units: str = "mm") -> int: ...

    @abstractmethod
    def microsteps_to_position(self, microsteps: int, units: str = "mm") -> float: ...


class IMotor(IMotorCore):
    """Extended per-axis motor surface — the full public method set of the
    concrete ``ZaberMotor`` class. Mocks implement this."""

    @abstractmethod
    def get_position(self, units: str) -> float: ...

    @abstractmethod
    def get_name(self) -> str: ...

    @abstractmethod
    def set_units(self, units: str) -> None: ...

    @abstractmethod
    def set_inverted(self, inverted: bool) -> None: ...

    @abstractmethod
    def set_limit_low(self, position: float, units: str) -> None: ...

    @abstractmethod
    def set_limit_high(self, position: float, units: str) -> None: ...

    @abstractmethod
    def set_origin(self, position: float, units: str) -> None: ...


class IMotorsCore(ABC):
    """Controller-reachable Motors container surface (D-05).

    The controller reads the per-axis motor handles as direct attributes —
    ``motors.vertical``, ``motors.horizontal``, ``motors.camera``. These are
    declared as ``@property`` + ``@abstractmethod`` slots (D-04).
    """

    # HAL error surface (AGENTS.md §10).
    error: int
    error_message: str

    @property
    @abstractmethod
    def vertical(self) -> IMotorCore: ...

    @property
    @abstractmethod
    def horizontal(self) -> IMotorCore: ...

    @property
    @abstractmethod
    def camera(self) -> IMotorCore: ...

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class IMotors(IMotorsCore):
    """Extended Motors container surface — the full public method set of the
    concrete ``Motors`` class. Mocks implement this."""

    @abstractmethod
    def get_properties(self) -> dict[str, str]: ...

    @abstractmethod
    def get_positions(self) -> dict[str, float]: ...


# =========================================================================== #
# ETLs family (container + per-lens Optotune)
# =========================================================================== #


class IETLsCore(ABC):
    """Controller-reachable ETLs container surface (D-05).

    The controller calls ``etls.open()``, ``etls.set_analog_mode()``, and
    ``etls.close()`` on the container. The per-lens Optotune handles are
    accessed via ``etls.etl_left`` / ``etls.etl_right`` (declared on the
    extended ABC since the controller does not read them directly today;
    the per-lens CRC commands are the IOptotune surface).
    """

    # HAL error surface (AGENTS.md §10).
    error: int
    error_message: str

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def set_analog_mode(self) -> None: ...


class IETLs(IETLsCore):
    """Extended ETLs container surface — the full public method set of the
    concrete ``ETLs`` class. Mocks implement this."""

    @abstractmethod
    def set_current_mode(self) -> None: ...

    @abstractmethod
    def get_mode(self) -> None: ...

    @abstractmethod
    def get_temperature(self) -> None: ...


class IOptotune(ABC):
    """Per-lens Optotune EL-10-30 surface — the ~30 CRC-protected serial
    commands (D-06).

    The concrete ``Optotune`` class (in ``lightsheet/hal/real/etls.py``)
    implements these against the real serial protocol. ``MockOptotune`` stubs
    each command with ``NotImplementedError`` (D-06) because the CRC protocol
    cannot be verified against real hardware on the Mac dev box; rig
    verification task HW2-01 covers them. A mock that silently succeeded
    would mask a real-device protocol regression, so the stubs raise rather
    than return a fake value.

    The methods mirror ``Optotune``'s public surface: connect / close /
    handshake, firmware identification, current limits, focal power, signal
    generator swing limits / frequency, temperature, status, EEPROM, mode.
    """

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def close(self, soft_close: bool | None = None) -> None: ...

    @abstractmethod
    def handshake(self) -> bytes: ...

    @abstractmethod
    def firmwaretype(self) -> int: ...

    @abstractmethod
    def firmwarebranch(self) -> int: ...

    @abstractmethod
    def partnumber(self) -> bytes: ...

    @abstractmethod
    def current_upper(self, value: float | None = None) -> float: ...

    @abstractmethod
    def current_lower(self, value: float | None = None) -> float: ...

    @abstractmethod
    def firmwareversion(self) -> str: ...

    @abstractmethod
    def deviceid(self) -> bytes: ...

    @abstractmethod
    def gain(
        self, value: float | None = None
    ) -> float | tuple[int, float, float]: ...

    @abstractmethod
    def serialnumber(self) -> bytes: ...

    @abstractmethod
    def current(self, value: float | None = None) -> float: ...

    @abstractmethod
    def siggen_upper(self, value: float | None = None) -> float: ...

    @abstractmethod
    def siggen_lower(self, value: float | None = None) -> float: ...

    @abstractmethod
    def siggen_freq(self, value: float | None = None) -> float: ...

    @abstractmethod
    def temp_limits(
        self, value: tuple[float, float] | None = None
    ) -> tuple[float, float]: ...

    @abstractmethod
    def focalpower(self, value: float | None = None) -> float: ...

    @abstractmethod
    def current_max(self, value: float | None = None) -> float: ...

    @abstractmethod
    def temp_reading(self) -> float: ...

    @abstractmethod
    def get_status(self) -> bytes: ...

    @abstractmethod
    def eeprom_read(self, value: int) -> int: ...

    @abstractmethod
    def analog_input(self) -> int: ...

    @abstractmethod
    def eeprom_write(self, address: int, value: int) -> int: ...

    @abstractmethod
    def eeprom_contents(self) -> bytes: ...

    @abstractmethod
    def mode(self, mode_str: str | None = None) -> str: ...
