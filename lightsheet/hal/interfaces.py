"""HAL interface ABCs for the lightsheet microscope device families.

Splits each hardware device family into three concerns: this module (the
abstract interfaces), ``lightsheet/hal/real/`` (vendor-bound concrete
implementations), and ``lightsheet/hal/mocks/`` (standalone mock
implementations used under ``--demo`` / ``LIGHTSHEET_DEMO=1``).

This module imports only ``abc`` — no vendor SDKs, no numpy.
"""

import threading
from abc import ABC, abstractmethod
from typing import Any


class ICameraCore(ABC):
    """Controller-reachable Camera surface.

    The controller reads camera state as direct attributes (``xsize``,
    ``ysize``, etc.) declared as class-level annotations, not abstract
    properties, because the real class sets them as plain instance attrs.
    """

    # HAL error surface — every HAL ABC declares these.
    error: int
    error_message: str

    # Controller-read attributes — class-level annotations.
    xsize: int | None
    ysize: int | None
    # Binning readback — the XY voxel-size source for the ZarrSaver's base_res.
    binning_x: int
    binning_y: int
    exposure_time: float
    shutter_mode: str
    line_time: float | None
    lightsheet_line_time: float
    lightsheet_exposed_lines: int
    lightsheet_delay_lines: int
    recorder_timeout_status: bool

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
    ``Camera`` class. Declared on the extended ABC so a mock that omits one
    fails ABC instantiation with a clear ``TypeError``."""

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
    def copy_recorder_images(self, number_of_images: int) -> Any | None: ...

    # Extended getters — the controller does not call these.
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
    def get_pixel_rates(self) -> dict[str, object] | list: ...  # ty: ignore[missing-type-argument]

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
    """Controller-reachable SigGen surface.

    The controller reads SigGen state as direct attributes (class-level
    annotations, not abstract properties — same pattern as ``ICameraCore``).
    """

    # HAL error surface.
    error: int
    error_message: str

    # Controller-read attributes — class-level annotations.
    galvo_left_amplitude: float
    galvo_right_amplitude: float
    galvo_left_offset: float
    galvo_right_offset: float
    galvo_activated: bool
    galvo_inverted: bool
    etl_left_amplitude: float
    etl_right_amplitude: float
    etl_left_offset: float
    etl_right_offset: float
    etl_activated: bool
    etl_steps: int
    sample_rate: float
    waveform_cycles: int | None
    waveform_metadata: dict | None  # ty: ignore[missing-type-argument]

    # open/close are NOT declared — the real SigGen class does not expose them.
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
    ``SigGen`` class."""

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

    # Extended config surface — the controller does not call these.
    @abstractmethod
    def cfg_load_ini(self) -> None: ...

    @abstractmethod
    def cfg_save_ini(self) -> None: ...


# =========================================================================== #
# Motors family (container + per-axis)
# =========================================================================== #


class IMotorCore(ABC):
    """Controller-reachable per-axis motor surface.

    The controller reads per-axis motor state as direct attributes (class-level
    annotations, not abstract properties — same pattern as ``ICameraCore``).
    Travel-limit enforcement is a physical-safety contract: ``move_absolute``
    / ``move_relative`` MUST raise ``ValueError`` on over-travel BEFORE any
    serial command.
    """

    # HAL error surface.
    error: int
    error_message: str

    # Controller-read attributes — class-level annotations.
    limit_low_microsteps: int
    limit_high_microsteps: int
    microstep_size: float
    device_number: int

    # move_absolute/move_relative raise ValueError on over-travel
    # before any serial command.
    @abstractmethod
    def move_absolute_position(self, absolute_position: float, units: str) -> None: ...

    @abstractmethod
    def move_relative_position(self, relative_position: float, units: str) -> None: ...

    @abstractmethod
    def position_to_microsteps(self, position: float, units: str = "mm") -> int: ...

    @abstractmethod
    def microsteps_to_position(self, microsteps: int, units: str = "mm") -> float: ...

    # Controller-called getters.
    @abstractmethod
    def get_limit_low(self, units: str) -> float: ...

    @abstractmethod
    def get_limit_high(self, units: str) -> float: ...

    @abstractmethod
    def get_origin(self, units: str) -> float: ...


class IMotor(IMotorCore):
    """Extended per-axis motor surface — the full public method set of the
    concrete ``ZaberMotor`` class."""

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
    """Controller-reachable Motors container surface.

    The controller reads per-axis motor handles as direct attributes
    (``vertical``, ``horizontal``, ``camera``) — class-level annotations.
    """

    # HAL error surface.
    error: int
    error_message: str

    # Controller-read attributes — class-level annotations.
    # The controller calls per-axis get_position/set_origin on these handles,
    # so the type is the extended ``IMotor`` surface, not ``IMotorCore``.
    vertical: "IMotor"
    horizontal: "IMotor"
    camera: "IMotor"


class IMotors(IMotorsCore):
    """Extended Motors container surface — the full public method set of the
    concrete ``Motors`` class. Both the real class and the mock inherit this."""

    @abstractmethod
    def get_properties(self) -> dict[str, str]: ...

    @abstractmethod
    def get_positions(self) -> dict[str, float]: ...

    @abstractmethod
    def close(self) -> None:
        """Close the shared serial handle. Called on app shutdown."""
        ...

    @abstractmethod
    def move_axes_parallel(self, moves: list[tuple[str, float, str]]) -> None:
        """Move multiple axes on the shared serial bus.

        Validates ALL targets against travel limits BEFORE any serial bytes
        are written. Raises ``ValueError`` if ANY axis is over-travel. Commands
        are sent back-to-back, then one 6-byte reply is read per command in
        send order.
        """

    # Extended config surface — the controller does not call these.
    @abstractmethod
    def cfg_load_ini(self) -> None: ...

    @abstractmethod
    def cfg_save_ini(self) -> None: ...


# =========================================================================== #
# ETLs family (container + per-lens Optotune)
# =========================================================================== #


class IETLsCore(ABC):
    """Controller-reachable ETLs container surface.

    The controller calls ``open()``, ``set_analog_mode()``, and ``close()``
    on the container; per-lens handles are on the extended ABC.
    """

    # HAL error surface.
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
    """Per-lens Optotune EL-10-30 surface — the CRC-protected serial commands.

    ``MockOptotune`` stubs each command with ``NotImplementedError`` because
    the CRC protocol cannot be verified without real hardware; a mock that
    silently succeeded would mask a real-device protocol regression.
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
# Power is mW-canonical at the interface: ``set_power(mw)`` takes milliwatts
# and ``power`` / ``max_power`` attrs are in mW. Each backend converts to its
# native unit internally. The two-layer safety clamp: ``set_power`` clamps mW
# to ``[0, max_power]``; each backend's native-unit write path clamps again.
#
# Controller-read attrs are class-level annotations (same pattern as
# ``ICameraCore``).
#
# ``off()`` is synchronous — the E-stop kill path. Concrete backends MUST set
# ``active=False`` and return ``None`` immediately, with no thread/queue
# offload.


class ILaser(ABC):
    """Unified single-channel laser ABC (mW-canonical).

    Each backend converts mW to its native unit internally and clamps the
    native-unit value inside its write path as a second, independent safety
    layer (two-layer clamp). ``off()`` is synchronous (E-stop kill path) —
    MUST return ``None`` immediately with no thread/queue offload.
    """

    # HAL error surface — every HAL ABC declares these.
    error: int
    error_message: str

    # Controller-read attributes — class-level annotations.
    wavelength: int  # nm
    power: float  # mW (canonical)
    max_power: float  # mW (canonical)
    active: bool  # live state for status indicator
    label: str  # e.g. "Laser 1 (555 nm)" for metadata
    # Whether get_output_power() returns a calibrated value (True) or a
    # linear-through-origin estimate (False).
    calibrated: bool

    # Per-instance RLock for daemon-thread write serialization. Reentrant so
    # _toggle_laser* can call _write_laser*_power under the same lock.
    # IBeamSmartLaser aliases the inner IBeam._lock for lock identity.
    _lock: threading.RLock

    # Optional back-reference to the shell's E-stop event. on() and set_power()
    # re-check it before the HAL write so a kill cannot be re-energized.
    _estop_event: threading.Event | None = None

    @abstractmethod
    def open(self) -> None:
        """Open the device connection. No-op for backends with no persistent
        connection (DAQLaser, MockLaser)."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release the device connection. No-op for backends with no
        persistent connection."""
        ...

    @abstractmethod
    def on(self) -> None:
        """Energize the laser (write the staged power to the device)."""
        ...

    @abstractmethod
    def off(self) -> None:
        """Synchronous E-stop kill path.

        MUST set ``active=False`` and return ``None`` immediately, with no
        thread/queue offload — offloading would break the synchronous-off
        safety contract for a Class IIIB laser.
        """
        ...

    @abstractmethod
    def set_power(self, mw: float) -> None:
        """Set the staged laser power in milliwatts (mW canonical).

        Clamps ``mw`` to ``[0.0, max_power]`` (mW) as the first safety layer.
        Each backend's native-unit write path clamps again as a second,
        independent safety layer (two-layer clamp).
        """
        ...

    @abstractmethod
    def get_output_power(self) -> float | None:
        """Read the current output power in milliwatts (mW).

        Returns the live hardware readback where supported, or the staged
        ``self.power`` where the backend has no readback. Returns ``None``
        on a readback failure so the caller can distinguish "no reading"
        from "reading is 0".
        """
        ...


# =========================================================================== #
# Power Meter family
# =========================================================================== #
#
# The ``IPowerMeter`` ABC is the read-only optical power measurement surface.
# It is a calibration/diagnostic instrument, not part of the ``DeviceBundle``.
# ``read_power`` returns watts (SI); callers convert to mW at the call site.


class IPowerMeter(ABC):
    """Read-only optical power meter ABC.

    Not part of the ``DeviceBundle`` — constructed directly by the calibration
    sweep script or a future monitoring widget. ``read_power`` returns watts.
    """

    # HAL error surface — every HAL ABC declares these.
    error: int
    error_message: str

    @abstractmethod
    def open(self) -> None:
        """Open the device connection. No-op for MockPowerMeter."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release the device connection. No-op for MockPowerMeter."""
        ...

    @abstractmethod
    def read_power(self) -> float:
        """Read the current optical power in watts (SI).

        Raises an exception on a read failure so the caller can distinguish
        a failed reading from a zero reading.
        """
        ...

    @abstractmethod
    def zero(self) -> None:
        """Perform a zero/dark offset adjustment (background subtraction).

        The sensor must be blocked when called. No-op for MockPowerMeter.
        """
        ...
