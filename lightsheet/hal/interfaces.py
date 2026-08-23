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
    def gain(self, value: float | None = None) -> float | tuple[int, float, float]: ...

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
# Unified single-channel Laser ABC (mW-canonical)
# =========================================================================== #
#
# The unified ``ILaser`` ABC adopts the member names
# (``on`` / ``off`` / ``set_power`` + ``wavelength`` / ``power`` /
# ``max_power`` / ``active`` / ``error`` / ``error_message`` attrs)
# — a single-channel ABC instantiated once per configured laser.
#
# Power is **mW-canonical at the interface** (D-01): ``set_power(mw)`` takes
# milliwatts and ``power`` / ``max_power`` attrs are in mW. Each backend
# converts to its native unit internally (DAQLaser: mW -> V via
# ``mw_per_volt``; IBeamSmartLaser: mW -> uW via *1000; MockLaser: tracks mW
# in software). The Class IIIB safety clamp (AGENTS.md §2) lives in the
# **native unit inside each backend** — the interface unit is a
# truthfulness/metadata decision, not a safety one. ``set_power`` clamps mW
# to ``[0, max_power]`` as a first safety layer; each backend's native-unit
# write path clamps again as a second, independent safety layer.
#
# Controller-read attrs are declared as **class-level annotations** (not
# ``@property`` + ``@abstractmethod``) — Python's ABC check runs at
# instantiation, before ``__init__`` sets instance attrs, and an abstract
# property descriptor is not satisfied by a plain instance attr (same
# pattern as ``ICameraCore``).
#
# ``off()`` is synchronous — the E-stop kill path (AGENTS.md §2). Concrete
# backends MUST set ``active=False`` (and ``power=0.0`` where appropriate)
# and return ``None`` immediately, with no thread/queue offload, so the
# GUI-thread E-stop handler can drive the laser off without waiting on a
# background task.


class ILaser(ABC):
    """Unified single-channel laser ABC (mW-canonical).

    The controller holds a ``list[ILaser]`` (one instance per configured
    laser). Each backend converts mW to its native unit internally and
    clamps the native-unit value inside its write path as a second,
    independent safety layer (AGENTS.md §2 — two-layer clamp).

    Controller-read attrs (``wavelength`` / ``power`` / ``max_power`` /
    ``active`` / ``label`` + the cross-cutting ``error`` / ``error_message``
    HAL error surface, AGENTS.md §10) are class-level annotations — the
    concrete backends set them as plain instance attributes in ``__init__``.

    ``off()`` is synchronous — the E-stop kill path (AGENTS.md §2). It MUST
    return ``None`` immediately, with no thread/queue offload, after
    setting ``active=False`` (and ``power=0.0`` where appropriate).
    """

    # HAL error surface (AGENTS.md §10) — every HAL ABC declares these.
    # Concrete classes set them as instance attributes in ``__init__``.
    error: int
    error_message: str

    # Controller-read attributes — class-level annotations. The real and
    # mock classes set them as plain instance attributes in __init__.
    wavelength: int  # nm
    power: float  # mW (canonical)
    max_power: float  # mW (canonical)
    active: bool  # live state for status indicator
    label: str  # e.g. "Laser 1 (561 nm)" for metadata

    # Lifecycle verbs (AGENTS.md §10) — abstract methods returning None.
    @abstractmethod
    def on(self) -> None:
        """Energize the laser (write the staged power to the device)."""
        ...

    @abstractmethod
    def off(self) -> None:
        """Synchronous E-stop kill path (AGENTS.md §2).

        MUST set ``active=False`` (and ``power=0.0`` where appropriate) and
        return ``None`` immediately, with no thread/queue offload. The
        GUI-thread E-stop handler calls this directly; offloading it would
        break the synchronous-off safety contract for a Class IIIB laser.
        """
        ...

    @abstractmethod
    def set_power(self, mw: float) -> None:
        """Set the staged laser power in milliwatts (mW canonical).

        Clamps ``mw`` to ``[0.0, max_power]`` (mW) as the first safety
        layer. Each backend's native-unit write path clamps again as a
        second, independent safety layer (AGENTS.md §2 — two-layer clamp).
        """
        ...
