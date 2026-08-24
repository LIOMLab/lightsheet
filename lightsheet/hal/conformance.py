"""TST-04 conformance contracts — the shared assertion body behind both
``[real, mock]`` parametrize ids (D-15).

Each device family has a ``ConformanceContract`` constant derived from its
core ABC (``lightsheet/hal/interfaces.py``). The parametrized conformance
tests (``test/test_<device>_conformance.py``) call ``assert_lifecycle`` /
``assert_error_surface`` / ``assert_read_attrs`` on whichever instance the
parametrize id produced — real or mock. One assertion body runs behind both
paths, so mock-vs-real drift is structurally caught: a mock that dropped a
lifecycle verb or a real class that renamed a controller-read attribute
fails the same assertion the other path passes.

The contract is derived from the core ABC, not hand-maintained per method
(D-15). ``assert_lifecycle`` checks every lifecycle method exists on the
instance (``hasattr``) and exercises only the safe idempotent ones
(``open`` / ``close``) — it does NOT call ``arm`` / ``start_recorder`` /
``create_scanner`` etc. because those have side effects (DAQ tasks, recorder
buffers) that are out of scope for a conformance smoke and would energize
hardware on the real path. The full lifecycle exercise is the rig-only
integration tests' job (``*_rig.py``, D-16).

Safety-critical behavior (Lasers power clamping, IBeam synchronous ``off()``)
is asserted in the per-device conformance test files, not here — the contract
module is the structural-surface check; the safety invariants are behavior
checks that belong alongside the device-specific test body.
"""

from dataclasses import dataclass


@dataclass
class ConformanceContract:
    """Methods and attributes a device family must expose (D-15).

    Derived from the core ABC (``ICameraCore`` / ``ISigGenCore`` / etc.) so
    the assertions are shared across families and the contract drifts with
    the ABC, not against it. Consumed by the parametrize fixture so one
    assertion body runs behind both ``[real, mock]``.

    Fields:
        lifecycle_methods: lifecycle verbs the instance must expose
            (``hasattr`` check). Only ``open`` / ``close`` are CALLED —
            the rest are existence checks (see module docstring).
        read_attrs: controller-read attributes the instance must populate
            (``hasattr`` check). The controller reads these as direct
            attributes (D-04), so a missing attr is a structural break.
        setter_methods: setter verbs the instance must expose
            (``hasattr`` check). Not called — setters may have side effects
            (DAQ writes, serial commands) outside conformance scope.
        getter_methods: read getter verbs the instance must expose
            (``hasattr`` check). Not called — getters may issue
            round-trips (serial reads, DAQ queries) outside conformance
            scope. Defaults to an empty tuple for families with no
            getters, so existing contracts continue to construct without
            the new field.
    """

    lifecycle_methods: tuple[str, ...]
    read_attrs: tuple[str, ...]
    setter_methods: tuple[str, ...]
    getter_methods: tuple[str, ...] = ()

    def assert_lifecycle(self, dev: object) -> None:
        """Assert every lifecycle method exists on ``dev`` and exercise the
        safe idempotent ones (``open`` / ``close`` if present).

        Does NOT call ``arm`` / ``start_*`` / ``create_*`` etc. — those have
        side effects (DAQ tasks, recorder buffers, serial commands) that
        are out of scope for a conformance smoke and would energize hardware
        on the real path. The full lifecycle exercise is the rig-only
        integration tests' job (``*_rig.py``, D-16).
        """
        for method in self.lifecycle_methods:
            assert hasattr(dev, method), (
                f"{type(dev).__name__} missing lifecycle method {method!r}"
            )
        # Exercise only the safe idempotent lifecycle verbs. These are
        # no-ops on the mock and open/close the device on the real path
        # (which is the rig's responsibility — the real param is skipped
        # on Mac via skipif, so this only runs on the rig where open/close
        # is safe).
        if hasattr(dev, "open"):
            dev.open()
        if hasattr(dev, "close"):
            dev.close()

    def assert_error_surface(self, dev: object) -> None:
        """Assert the cross-cutting HAL error surface (AGENTS.md §10) is
        present — ``error`` and ``error_message`` attributes. Every HAL
        class (real or mock) sets these in ``__init__`` so the controller's
        ``if self.<hal>.error`` checks work unchanged."""
        assert hasattr(dev, "error"), (
            f"{type(dev).__name__} missing HAL error surface attribute 'error'"
        )
        assert hasattr(dev, "error_message"), (
            f"{type(dev).__name__} missing HAL error surface attribute 'error_message'"
        )

    def assert_read_attrs(self, dev: object) -> None:
        """Assert every controller-read attribute exists on ``dev`` (D-04).
        The controller reads these as direct attributes, so a missing attr
        is a structural break that would surface as an ``AttributeError``
        in the controller's startup or per-frame path."""
        for attr in self.read_attrs:
            assert hasattr(dev, attr), (
                f"{type(dev).__name__} missing controller-read attribute {attr!r}"
            )

    def assert_setter_methods(self, dev: object) -> None:
        """Assert every setter method exists on ``dev`` (``hasattr`` check).
        Setters are NOT called — they may have side effects (DAQ writes,
        serial commands) outside conformance scope. A missing setter is a
        structural break that would surface as an ``AttributeError`` when
        the controller invokes it."""
        for method in self.setter_methods:
            assert hasattr(dev, method), (
                f"{type(dev).__name__} missing setter method {method!r}"
            )

    def assert_getter_methods(self, dev: object) -> None:
        """Assert every getter method exists on ``dev`` (``hasattr`` check).
        Getters are NOT called — they may issue round-trips (serial reads,
        DAQ queries) outside conformance scope. A missing getter is a
        structural break that would surface as an ``AttributeError`` when
        the controller invokes it. No-op when ``getter_methods`` is empty
        (the default), so families with no getters are unaffected."""
        for method in self.getter_methods:
            assert hasattr(dev, method), (
                f"{type(dev).__name__} missing getter method {method!r}"
            )


# --------------------------------------------------------------------------- #
# Per-device contract constants (D-15 — derived from the core ABCs in
# lightsheet/hal/interfaces.py).
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
    # read_attrs mirrors every class-level annotation declared on ICameraCore
    # (D-15 — the contract is the structural drift catch, so it must be at
    # least as strict as the ABC). error / error_message are the cross-cutting
    # HAL error surface (AGENTS.md §10) declared on the ABC.
    read_attrs=(
        "xsize",
        "ysize",
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
    # read_attrs mirrors every class-level annotation declared on ISigGenCore
    # (D-15). The previous contract listed only the galvo amplitudes + error
    # surface, so a mock that dropped an ETL attr or waveform_cycles/
    # waveform_metadata would pass conformance — weakening the drift catch.
    # Complete the list to match the ABC.
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
    # The Motors container ABC (IMotorsCore) declares only the per-axis
    # handles (vertical/horizontal/camera) + the error surface. The
    # per-axis IMotorCore read attrs (limit_low_microsteps etc.) are
    # covered by the per-axis mock-abc conformance test, not the
    # container contract.
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
# the setter contract because the controller calls it (the controller holds
# ``list[ILaser]`` and invokes ``set_power(mw)`` on each instance). ``on``
# / ``off`` are existence checks only — they have side effects (DAQ writes,
# serial commands) outside conformance scope; the synchronous-off +
# two-layer-clamp safety invariants are behavior checks that live in the
# per-device conformance test file. ``open`` / ``close`` are the HAL
# lifecycle verbs (AGENTS.md §10) the controller calls in ``hardware_init``
# and ``closeEvent`` — they are exercised by ``assert_lifecycle`` (no-ops
# on DAQLaser / MockLaser, real open/close on IBeamSmartLaser which is
# skipped on Mac). ``get_output_power`` is a read getter (not a setter);
# it is an existence check here (it issues a serial round-trip on the real
# iBeam), in the ``getter_methods`` tuple so the categorization matches
# the semantics. The per-device test files exercise the mW/None behavior.
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
