"""Conformance contracts — the shared assertion body behind ``[real, mock]``
parametrize ids.

Each device family has a ``ConformanceContract`` constant derived from its
core ABC. The parametrized conformance tests call ``assert_lifecycle`` /
``assert_error_surface`` / ``assert_read_attrs`` on whichever instance the
parametrize id produced — real or mock. One assertion body runs behind both
paths, so mock-vs-real drift is structurally caught.

``assert_lifecycle`` checks every lifecycle method exists and exercises only
the safe idempotent ones (``open`` / ``close``) — it does NOT call ``arm`` /
``start_recorder`` / ``create_scanner`` etc. because those have side effects
that would energize hardware on the real path.
"""

from dataclasses import dataclass


@dataclass
class ConformanceContract:
    """Methods and attributes a device family must expose.

    Derived from the core ABC so the assertions are shared across families
    and the contract drifts with the ABC, not against it.

    Fields:
        lifecycle_methods: lifecycle verbs the instance must expose
            (``hasattr`` check). Only ``open`` / ``close`` are CALLED.
        read_attrs: controller-read attributes the instance must populate
            (``hasattr`` check).
        setter_methods: setter verbs the instance must expose
            (``hasattr`` check). Not called.
        getter_methods: read getter verbs the instance must expose
            (``hasattr`` check). Not called. Defaults to empty tuple.
    """

    lifecycle_methods: tuple[str, ...]
    read_attrs: tuple[str, ...]
    setter_methods: tuple[str, ...]
    getter_methods: tuple[str, ...] = ()

    def assert_lifecycle(self, dev: object) -> None:
        """Assert every lifecycle method exists on ``dev`` and exercise the
        safe idempotent ones (``open`` / ``close`` if present)."""
        for method in self.lifecycle_methods:
            assert hasattr(dev, method), (
                f"{type(dev).__name__} missing lifecycle method {method!r}"
            )
        # Exercise only the safe idempotent lifecycle verbs.
        if hasattr(dev, "open"):
            dev.open()  # ty: ignore[call-non-callable]
        if hasattr(dev, "close"):
            dev.close()  # ty: ignore[call-non-callable]

    def assert_error_surface(self, dev: object) -> None:
        """Assert the cross-cutting HAL error surface is present — ``error``
        and ``error_message`` attributes."""
        assert hasattr(dev, "error"), (
            f"{type(dev).__name__} missing HAL error surface attribute 'error'"
        )
        assert hasattr(dev, "error_message"), (
            f"{type(dev).__name__} missing HAL error surface attribute 'error_message'"
        )

    def assert_read_attrs(self, dev: object) -> None:
        """Assert every controller-read attribute exists on ``dev``."""
        for attr in self.read_attrs:
            assert hasattr(dev, attr), (
                f"{type(dev).__name__} missing controller-read attribute {attr!r}"
            )

    def assert_setter_methods(self, dev: object) -> None:
        """Assert every setter method exists on ``dev`` (``hasattr`` check).
        Setters are NOT called -- they may have side effects outside
        conformance scope."""
        for method in self.setter_methods:
            assert hasattr(dev, method), (
                f"{type(dev).__name__} missing setter method {method!r}"
            )

    def assert_getter_methods(self, dev: object) -> None:
        """Assert every getter method exists on ``dev`` (``hasattr`` check).
        Getters are NOT called -- they may issue round-trips outside
        conformance scope."""
        for method in self.getter_methods:
            assert hasattr(dev, method), (
                f"{type(dev).__name__} missing getter method {method!r}"
            )


# --------------------------------------------------------------------------- #
# Per-device contract constants — derived from the core ABCs in interfaces.py.
# --------------------------------------------------------------------------- #

CAMERA_CONTRACT = ConformanceContract(
    lifecycle_methods=(
        "open",
        "close",
        "arm",
        "disarm",
        "arm_scan",
        "start_recorder",
        "monitor_recorder",
        "stop_recorder",
        "delete_recorder",
    ),
    # read_attrs mirrors every class-level annotation declared on ICameraCore.
    # error / error_message are the cross-cutting HAL error surface.
    read_attrs=(
        "xsize",
        "ysize",
        "binning_x",
        "binning_y",
        "exposure_time",
        "shutter_mode",
        "line_time",
        "lightsheet_exposed_lines",
        "lightsheet_delay_lines",
        "recorder_timeout_status",
        "error",
        "error_message",
    ),
    setter_methods=("set_exposure_time",),
)

SIGGEN_CONTRACT = ConformanceContract(
    lifecycle_methods=(
        "compute_scan_waveforms",
        "create_scanner",
        "start_scanner",
        "stop_scanner",
        "delete_scanner",
    ),
    # read_attrs mirrors every class-level annotation declared on ISigGenCore.
    read_attrs=(
        "galvo_left_amplitude",
        "galvo_right_amplitude",
        "galvo_left_offset",
        "galvo_right_offset",
        "etl_left_amplitude",
        "etl_right_amplitude",
        "etl_left_offset",
        "etl_right_offset",
        "waveform_cycles",
        "waveform_metadata",
        "error",
        "error_message",
    ),
    setter_methods=(),
)

MOTORS_CONTRACT = ConformanceContract(
    lifecycle_methods=(),
    # The Motors container ABC declares only the per-axis handles + error
    # surface. Per-axis read attrs are covered by the per-axis conformance test.
    read_attrs=(
        "vertical",
        "horizontal",
        "camera",
        "error",
        "error_message",
    ),
    setter_methods=(),
)

ETLS_CONTRACT = ConformanceContract(
    lifecycle_methods=("open", "close", "set_analog_mode"),
    read_attrs=("error", "error_message"),
    setter_methods=(),
)

# Unified single-channel ILaser surface (mW-canonical). ``set_power`` IS in
# the setter contract because the controller calls it. ``on`` / ``off`` are
# existence checks only (side effects outside conformance scope); the
# synchronous-off + two-layer-clamp safety invariants are behavior checks in
# the per-device conformance test file. ``get_output_power`` is a read getter
# (existence check here).
LASER_CONTRACT = ConformanceContract(
    lifecycle_methods=("on", "off", "open", "close"),
    read_attrs=(
        "wavelength",
        "power",
        "max_power",
        "active",
        "label",
        "error",
        "error_message",
        "_lock",
    ),
    setter_methods=("set_power",),
    getter_methods=("get_output_power",),
)

# IPowerMeter surface — read-only calibration instrument (not part of the
# DeviceBundle). ``zero`` is a lifecycle verb with side effects (existence
# check only). ``read_power`` / ``read_power_mw`` / ``read_averaged`` are
# read getters (existence checks only).
POWER_METER_CONTRACT = ConformanceContract(
    lifecycle_methods=("open", "close", "zero"),
    read_attrs=("error", "error_message"),
    setter_methods=(),
    getter_methods=("read_power", "read_power_mw", "read_averaged"),
)
