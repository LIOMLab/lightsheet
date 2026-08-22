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
