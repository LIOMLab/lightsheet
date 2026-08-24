"""Test-side abstract conformance base — the parallel of the HAL
``ICamera``->``Camera``/``MockCamera`` split (D-03).

``lightsheet/hal/conformance.py`` defines the production-side
``ConformanceContract`` dataclass + per-device contract constants
(``LASER_CONTRACT`` / ``CAMERA_CONTRACT`` / ...). That module stays
production-only — it is imported by both real and mock HAL modules at
runtime and must not couple to pytest.

This module is the TEST-side mirror: an abstract test base
(``DeviceConformanceBase``) that concrete per-environment test classes
(Mac mock / rig real) subclass, supplying a ``device_factory`` and a
``contract``. The five ``test_*`` methods each call the corresponding
``ConformanceContract.assert_*`` against a freshly constructed device.
One assertion body runs behind both environments, so mock-vs-real drift
is structurally caught — the same D-15 structural-surface check the
parametrized ``test_<device>_conformance.py`` files perform, now
expressed as an inheritable base for the per-environment concrete tests.

This is a BEHAVIOR test base (AGENTS.md §5): the ``assert_*`` calls
exercise the real device surface (``hasattr`` + safe idempotent
``open``/``close``); it is not a static-source grep.
"""

from collections.abc import Callable

from lightsheet.hal.conformance import ConformanceContract


class DeviceConformanceBase:
    """Abstract conformance test base — concrete subclasses set
    ``device_factory`` and ``contract``, the five ``test_*`` methods run
    the contract's ``assert_*`` against a freshly constructed device.

    Subclass pattern (per environment):

        class MockLaserConformance(DeviceConformanceBase):
            device_factory = staticmethod(_make_mock_l1)
            contract = LASER_CONTRACT

    The five methods mirror the five ``ConformanceContract.assert_*``
    entry points 1:1 so a concrete subclass gets the full structural
    drift catch by inheriting them.
    """

    # Set by concrete subclasses. ``device_factory`` is a zero-arg
    # callable returning a fresh device instance; ``contract`` is the
    # production-side ConformanceContract constant for the device family.
    device_factory: Callable[[], object]
    contract: ConformanceContract

    def test_lifecycle(self) -> None:
        self.contract.assert_lifecycle(self.device_factory())

    def test_error_surface(self) -> None:
        self.contract.assert_error_surface(self.device_factory())

    def test_read_attrs(self) -> None:
        self.contract.assert_read_attrs(self.device_factory())

    def test_setter_methods(self) -> None:
        self.contract.assert_setter_methods(self.device_factory())

    def test_getter_methods(self) -> None:
        self.contract.assert_getter_methods(self.device_factory())
