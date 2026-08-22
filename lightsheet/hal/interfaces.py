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
  those attributes are declared here as **class-level annotations** (not
  ``@property`` + ``@abstractmethod`` slots). The real classes implement
  them as plain instance attributes set in ``__init__``/``open``, and a
  ``@property`` + ``@abstractmethod`` slot is NOT satisfied by a plain
  instance attribute (Python's ABC check runs at instantiation, before
  ``__init__``, and an abstract property descriptor requires a class-level
  override, not an instance attr). The class-level annotation preserves the
  type-checker hint for Phase 5 DI without blocking real-class inheritance.
  Phase 5 dependency-injection seams type-hint against the core ABC.
- ``ICamera`` is the **extended** ABC — the full public method surface of
  the concrete ``Camera`` class. Both the real class and the mock inherit
  the extended ABC (which transitively inherits the core ABC); the TST-04
  conformance parametrization runs the same assertions behind both
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
    These are declared as **class-level annotations** (not ``@property`` +
    ``@abstractmethod`` slots) because the real ``Camera`` class implements
    them as plain instance attributes set in ``__init__``/``open``. A
    ``@property`` + ``@abstractmethod`` slot is NOT satisfied by a plain
    instance attribute (Python's ABC check runs at instantiation, before
    ``__init__``, and an abstract property descriptor requires a class-level
    override, not an instance attr). The class-level annotation preserves
    the type-checker hint for Phase 5 DI without blocking real-class
    inheritance.

    The cross-cutting HAL error surface (``error`` / ``error_message``,
    AGENTS.md §10) is declared as a class-level annotation so every concrete
    Camera (real or mock) carries it.
    """

    # HAL error surface (AGENTS.md §10) — every HAL ABC declares these.
    # Concrete classes set them as instance attributes in ``__init__``.
    error: int
    error_message: str

    # Controller-read attributes (D-04) — class-level annotations. The real
    # and mock classes set them as plain instance attributes in __init__/open.
    xsize: int | None
    ysize: int | None
    exposure_time: float
    shutter_mode: str
    line_time: float | None
    lightsheet_exposed_lines: int
    lightsheet_delay_lines: int
    recorder_timeout_status: bool

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
    ``Camera`` class. Both the real class and the mock inherit this; TST-04
    conformance parametrization runs against this surface behind both
    ``[real, mock]``.

    These getters and config methods are the full public surface the
    Properties dialog and future rig integration tests exercise, not the
    controller call graph (the controller calls only ``get_properties``).
    They are declared on the extended ABC so a mock that omits one fails
    ABC instantiation with a clear ``TypeError`` instead of crashing at
    runtime.
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
    def set_trigger_mode(self, trigger_mode: str) -> None: ...

    @abstractmethod
    def set_lightsheet_mode(self) -> None: ...

    @abstractmethod
    def get_name(self) -> str | None: ...

    @abstractmethod
    def get_properties(self) -> dict[str, object]: ...

    @abstractmethod
    def copy_recorder_images(self, number_of_images: int) -> Any: ...

    # Extended getters — the full public getter/config surface of the real
    # Camera class. The controller does not call these; the Properties dialog
    # and rig integration tests do.
    @abstractmethod
    def get_trigger_mode(self) -> str | None: ...

    @abstractmethod
    def get_acquire_mode(self) -> str | None: ...

    @abstractmethod
    def get_storage_mode(self) -> str | None: ...

    @abstractmethod
    def get_recorder_submode(self) -> str | None: ...

    @abstractmethod
    def get_exposure_time(self) -> int | None: ...

    @abstractmethod
    def get_exposure_timebase(self) -> str | None: ...

    @abstractmethod
    def get_delay_time(self) -> int | None: ...

    @abstractmethod
    def get_delay_timebase(self) -> str | None: ...

    @abstractmethod
    def get_pixel_rates(self) -> dict[str, object] | list: ...

    @abstractmethod
    def get_pixel_rate(self) -> str | None: ...

    @abstractmethod
    def get_readout_format(self) -> str | None: ...

    @abstractmethod
    def cfg_load_ini(self) -> None: ...

    @abstractmethod
    def cfg_save_ini(self) -> None: ...


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
    ``self.siggen.waveform_metadata``. These are declared as **class-level
    annotations** (not ``@property`` + ``@abstractmethod`` slots) because
    the real ``SigGen`` class implements them as plain instance attributes
    set in ``__init__``. A ``@property`` + ``@abstractmethod`` slot is NOT
    satisfied by a plain instance attribute (Python's ABC check runs at
    instantiation, before ``__init__``). The class-level annotation preserves
    the type-checker hint for Phase 5 DI without blocking real-class
    inheritance.

    The cross-cutting HAL error surface (``error`` / ``error_message``,
    AGENTS.md §10) is declared as a class-level annotation.

    ``arm`` / ``disarm`` are NOT declared here: the real ``SigGen`` class
    does not implement them and the controller never calls them. The ABC
    is pinned to that call graph.
    """

    # HAL error surface (AGENTS.md §10).
    error: int
    error_message: str

    # Controller-read attributes (D-04) — class-level annotations. The real
    # and mock classes set them as plain instance attributes in __init__.
    galvo_left_amplitude: float
    galvo_right_amplitude: float
    galvo_left_offset: float
    galvo_right_offset: float
    etl_left_amplitude: float
    etl_right_amplitude: float
    etl_left_offset: float
    etl_right_offset: float
    waveform_cycles: int | None
    waveform_metadata: dict | None

    # Lifecycle verbs (AGENTS.md §10) — abstract methods returning None.
    # ``open`` / ``close`` are NOT declared here: the real ``SigGen`` class
    # initializes the DAQ in ``__init__`` and does not expose open/close
    # lifecycle verbs; the controller never calls them. The ABC is pinned
    # to that call graph. Concrete mock classes may still expose them as
    # no-op extras.
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
    ``SigGen`` class. Both the real class and the mock inherit this; TST-04
    conformance parametrization runs against this surface behind both
    ``[real, mock]``.
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

    # Extended config surface — the controller does not call these; the
    # real SigGen exposes them for config.ini load/save.
    @abstractmethod
    def cfg_load_ini(self) -> None: ...

    @abstractmethod
    def cfg_save_ini(self) -> None: ...


# =========================================================================== #
# Motors family (container + per-axis)
# =========================================================================== #


class IMotorCore(ABC):
    """Controller-reachable per-axis motor surface (D-05).

    The controller reads per-axis motor state as direct attributes —
    ``motor.limit_low_microsteps``, ``motor.limit_high_microsteps``,
    ``motor.microstep_size``, ``motor.device_number``. These are declared
    as **class-level annotations** (not ``@property`` + ``@abstractmethod``
    slots) because the real ``ZaberMotor`` class implements them as plain
    instance attributes set in ``__init__``. The controller queries position
    via ``get_position(units)`` (a serial command on the real Zaber stage),
    never as a direct ``motor.position`` attribute, so ``position`` is NOT
    part of the core ABC contract — concrete classes may expose it as a
    plain attribute (the mock does, for software tracking) but the ABC is
    pinned to the controller's actual call graph.

    The 3 getters ``get_limit_low`` / ``get_limit_high`` / ``get_origin``
    are declared on the core ABC because the controller's
    ``updateUi_units`` / ``updateUi_check_positions`` /
    ``updateUi_check_stepsize`` / ``updateUi_set_origin`` /
    ``updateUi_set_focus`` / ``updateUi_set_colormap`` call graph reads
    them (46 call sites). They are the controller-called surface, so they
    belong on the core ABC that Phase 5 DI type-hints against.

    Travel-limit enforcement (AGENTS.md §2) is a physical-safety contract:
    ``move_absolute_position`` and ``move_relative_position`` MUST raise
    ``ValueError`` on over-travel BEFORE any state change or serial command.
    Concrete classes (real ``ZaberMotor`` and ``MockMotor``) implement this.
    """

    # HAL error surface (AGENTS.md §10).
    error: int
    error_message: str

    # Controller-read attributes (D-04) — class-level annotations. The real
    # and mock classes set them as plain instance attributes in __init__.
    limit_low_microsteps: int
    limit_high_microsteps: int
    microstep_size: float
    device_number: int

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

    # Controller-called getters (D-05 core — 46 call sites in controller.py:
    # updateUi_units / updateUi_check_positions / updateUi_check_stepsize /
    # updateUi_set_origin / updateUi_set_focus / updateUi_set_colormap).
    @abstractmethod
    def get_limit_low(self, units: str) -> float: ...

    @abstractmethod
    def get_limit_high(self, units: str) -> float: ...

    @abstractmethod
    def get_origin(self, units: str) -> float: ...


class IMotor(IMotorCore):
    """Extended per-axis motor surface — the full public method set of the
    concrete ``ZaberMotor`` class. Both the real class and the mock inherit
    this.

    ``get_units`` / ``get_inverted`` are part of the real ``ZaberMotor``
    public surface but not the controller call graph. ``ask_id`` /
    ``move_home`` are real-class lifecycle extras not GUI-wired today. They
    are declared on the extended ABC so a mock that omits one fails ABC
    instantiation with a clear ``TypeError`` instead of crashing at runtime.
    """

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

    # Extended getters — real ZaberMotor public surface, not controller-called.
    @abstractmethod
    def get_units(self) -> str: ...

    @abstractmethod
    def get_inverted(self) -> bool: ...

    # Real-class lifecycle extras — not GUI-wired today.
    @abstractmethod
    def ask_id(self) -> int: ...

    @abstractmethod
    def move_home(self) -> None: ...


class IMotorsCore(ABC):
    """Controller-reachable Motors container surface (D-05).

    The controller reads the per-axis motor handles as direct attributes —
    ``motors.vertical``, ``motors.horizontal``, ``motors.camera``. These are
    declared as **class-level annotations** (not ``@property`` +
    ``@abstractmethod`` slots) because the real ``Motors`` class implements
    them as plain instance attributes set in ``__init__`` (via the per-axis
    ``ZaberMotor`` constructors).

    The real ``Motors`` class does not expose ``open()`` / ``close()``
    lifecycle verbs; the controller never calls them. The ABC is pinned to
    that call graph, so ``open`` / ``close`` are NOT declared here. Concrete
    mock classes may still expose them as no-op extras.
    """

    # HAL error surface (AGENTS.md §10).
    error: int
    error_message: str

    # Controller-read attributes (D-04) — class-level annotations. The real
    # and mock classes set them as plain instance attributes in __init__.
    vertical: "IMotorCore"
    horizontal: "IMotorCore"
    camera: "IMotorCore"


class IMotors(IMotorsCore):
    """Extended Motors container surface — the full public method set of the
    concrete ``Motors`` class. Both the real class and the mock inherit this."""

    @abstractmethod
    def get_properties(self) -> dict[str, str]: ...

    @abstractmethod
    def get_positions(self) -> dict[str, float]: ...

    # Extended config surface — the controller does not call these; the
    # real Motors exposes them for config.ini load/save.
    @abstractmethod
    def cfg_load_ini(self) -> None: ...

    @abstractmethod
    def cfg_save_ini(self) -> None: ...


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


# =========================================================================== #
# Lasers family (NI-DAQ AO, 2 channels)
# =========================================================================== #
#
# Phase 3 mocks the existing concrete ``Lasers`` class behind per-device ABCs
# (``ILasersCore`` / ``ILasers``) in the same shape as the other device
# families — NO unified ``ILaser`` ABC this phase. The member names here
# (``on`` / ``off`` / ``set_power`` + ``wavelength`` / ``power`` /
# ``max_power`` / ``active`` attrs) are chosen so the future unified
# ``ILaser`` ABC can adopt them unchanged — the Phase 4 refactor is a
# re-wrap, not a rename.
#
# The concrete ``Lasers`` class exposes a 2-channel surface
# (``laser1_*`` / ``laser2_*``) rather than a single-channel ``on``/``off``/
# ``set_power`` surface. The ABC mirrors that 2-channel surface exactly
# (``laser1_on`` / ``laser1_off`` / ``laser2_on`` / ``laser2_off`` +
# ``set_power(channel, value)``) so the controller's existing call sites
# (``self.lasers.laser1_on()`` etc.) type-check unchanged. Phase 4's
# ``ILaser`` will split the per-channel surface into a single-channel ABC
# instantiated twice; the member names picked here are what that split will
# adopt.


class ILasersCore(ABC):
    """Controller-reachable Lasers surface (D-05: pinned to controller call graph).

    The controller (``lightsheet/gui/controller.py``) reads Lasers state as
    *direct attributes* — ``self.lasers.laser1_wavelength``,
    ``self.lasers.laser2_wavelength``, ``self.lasers.laser1_max_power``,
    ``self.lasers.laser2_max_power``, ``self.lasers.laser1_power``,
    ``self.lasers.laser2_power``, ``self.lasers.laser1_active``,
    ``self.lasers.laser2_active``. These are declared as **class-level
    annotations** (not ``@property`` + ``@abstractmethod`` slots) because
    the real ``Lasers`` class implements them as plain instance attributes
    set in ``__init__``. The class-level annotation preserves the
    type-checker hint for Phase 5 DI without blocking real-class inheritance.

    The cross-cutting HAL error surface (``error`` / ``error_message``,
    AGENTS.md §10) is declared as a class-level annotation.

    Member names (``laser1_on`` / ``laser1_off`` / ``laser2_on`` /
    ``laser2_off`` + ``wavelength`` / ``power`` / ``max_power`` / ``active``
    attrs) are chosen so the future unified ``ILaser`` ABC can adopt them
    unchanged — Phase 4's refactor is a re-wrap, not a rename.
    """

    # HAL error surface (AGENTS.md §10).
    error: int
    error_message: str

    # Controller-read attributes (D-04) — class-level annotations. The real
    # and mock classes set them as plain instance attributes in __init__.
    laser1_wavelength: int
    laser2_wavelength: int
    laser1_max_power: float
    laser2_max_power: float
    laser1_power: float
    laser2_power: float
    laser1_active: bool
    laser2_active: bool

    # Lifecycle verbs (AGENTS.md §10) — abstract methods returning None.
    # The 2-channel on/off surface mirrors the concrete Lasers class; Phase 4
    # splits this into a single-channel ILaser instantiated twice.
    @abstractmethod
    def laser1_on(self) -> None: ...

    @abstractmethod
    def laser1_off(self) -> None: ...

    @abstractmethod
    def laser2_on(self) -> None: ...

    @abstractmethod
    def laser2_off(self) -> None: ...


class ILasers(ILasersCore):
    """Extended Lasers surface — the full public method set of the concrete
    ``Lasers`` class. Mocks implement this; the TST-04 conformance
    parametrization runs against this surface behind both ``[real, mock]``.

    Power clamping (AGENTS.md §2 — physical-safety control for a Class
    IIIB laser) happens inside the concrete ``Lasers._update_setpoints``
    (clamps via ``min(value, max_power)``) and inside ``MockLasers.set_power``.
    ``set_power(channel, value)`` is NOT part of the ABC contract today:
    the real ``Lasers`` class does not implement it (the controller sets
    ``self.lasers.laser1_power = volts`` directly and calls
    ``laser1_on()``), so declaring it on the ABC would make the real class
    fail its own ABC. ``MockLasers.set_power`` is kept as a concrete extra
    for the demo path and for the power-clamp safety test. A future
    refactor that adds ``set_power`` to the real ``Lasers`` class can
    re-add it to the ABC.

    ``_update_setpoints`` is a private implementation detail of the
    concrete ``Lasers`` class (the leading underscore convention); it is
    NOT part of the controller-facing surface and is not declared on the
    ABC. ``MockLasers`` implements it as a concrete method.
    """

    @abstractmethod
    def laser1_toggle(self) -> None: ...

    @abstractmethod
    def laser2_toggle(self) -> None: ...


# =========================================================================== #
# IBeam family (Toptica iBeam Smart serial, single channel)
# =========================================================================== #
#
# Same re-wrap-not-rename contract as Lasers: the member names here
# (``on`` / ``off`` / ``set_power`` + ``wavelength`` / ``power`` /
# ``max_power`` / ``error`` / ``active`` attrs) are what Phase 4's unified
# ``ILaser`` ABC will adopt unchanged.


class IIBeamCore(ABC):
    """Controller-reachable IBeam surface (D-05: pinned to controller call graph).

    The controller (``lightsheet/gui/controller.py``) reads IBeam state as
    *direct attributes* — ``self.ibeam.wavelength``, ``self.ibeam.max_power``,
    ``self.ibeam.error``. The internal ``_power`` / ``_is_on`` state is
    declared as **class-level annotations** (not ``@property`` +
    ``@abstractmethod`` slots) so the concrete class's internal-state surface
    is part of the contract (the controller's E-stop path reads
    ``ibeam._is_on`` indirectly via ``ibeam.off()``). The real and mock
    classes set them as plain instance attributes in ``__init__``.

    The cross-cutting HAL error surface (``error`` / ``error_message``,
    AGENTS.md §10) is declared as a class-level annotation.

    ``off()`` is the E-stop kill path (AGENTS.md §2 — Class IIIB laser
    safety): it MUST be synchronous (set ``_is_on=False`` and return None
    immediately, no queue/thread offload) so the GUI-thread E-stop handler
    can drive the laser off without waiting on a background task. The
    concrete ``IBeam.off()`` and ``MockIBeam.off()`` both preserve this
    contract.

    ``set_power(value)`` MUST clamp to ``max_power`` at the HAL boundary
    (AGENTS.md §2 — physical-safety control). The concrete ``IBeam.set_power``
    and ``MockIBeam.set_power`` both preserve the clamp.
    """

    # HAL error surface (AGENTS.md §10).
    error: int
    error_message: str

    # Controller-read attributes (D-04) — class-level annotations. The real
    # and mock classes set them as plain instance attributes in __init__.
    wavelength: int
    max_power: int

    # Internal state — declared on the core ABC so the synchronous-off /
    # power-clamp safety contracts are part of the typed surface. Class-level
    # annotations (not @property + @abstractmethod) because the real and mock
    # classes set them as plain instance attributes in __init__.
    _power: int
    _is_on: bool

    # Lifecycle verbs (AGENTS.md §10). off() is synchronous — E-stop kill
    # path (AGENTS.md §2). set_power clamps to max_power (AGENTS.md §2).
    @abstractmethod
    def on(self) -> None: ...

    @abstractmethod
    def off(self) -> None: ...

    @abstractmethod
    def set_power(self, power_uw: int) -> None: ...

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def enable_channel(self, channel: int | None = None) -> None: ...


class IIBeam(IIBeamCore):
    """Extended IBeam surface — the full public method set of the concrete
    ``IBeam`` class. Both the real class and the mock inherit this; TST-04
    conformance parametrization runs against this surface behind both
    ``[real, mock]``.
    """

    @abstractmethod
    def reboot(self) -> None: ...

    @abstractmethod
    def get_output_power(self) -> int: ...

    @abstractmethod
    def is_enabled(self) -> bool: ...
