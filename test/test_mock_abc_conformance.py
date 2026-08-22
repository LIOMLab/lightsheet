"""
Conformance tests for the Mock* HAL classes against their ABCs.

The Phase 3 tracer slice wires the Camera family end-to-end: a standalone
``MockCamera`` class that implements ``ICamera`` (and through inheritance
``ICameraCore``), constructed with no hardware. These tests prove the ABC
contract holds at runtime — ``isinstance(MockCamera(), ICamera)`` and
``isinstance(MockCamera(), ICameraCore)`` — and that the controller-reachable
HAL error surface (``error`` / ``error_message``) plus the controller-read
attributes (``xsize`` / ``ysize``) are populated.

Direct import + construct style mirrors ``test/test_motor_limits.py`` and
``test/test_ibeam.py``: mocks construct with no hardware, so no ``__new__``
bypass is needed (the whole point of mocks per AGENTS.md §5).
"""

from lightsheet.hal import ICamera, ICameraCore, MockCamera


def test_mock_camera_is_icamera() -> None:
    """MockCamera must be an ICamera (and through inheritance an ICameraCore)
    so the controller's HAL-typed seams accept it unchanged."""
    cam = MockCamera()
    assert isinstance(cam, ICamera)
    assert isinstance(cam, ICameraCore)


def test_mock_camera_has_hal_error_surface() -> None:
    """A freshly-constructed MockCamera carries the cross-cutting HAL error
    surface (AGENTS.md §10) in the cleared state — the controller's
    ``if self.camera.error`` checks must see 0 on a healthy construct."""
    cam = MockCamera()
    assert cam.error == 0
    assert cam.error_message == ""


def test_mock_camera_populates_controller_read_attrs() -> None:
    """The controller reads ``camera.xsize`` / ``camera.ysize`` as direct
    attributes (D-04). A MockCamera must populate them on construct (via
    its ``open()`` synthetic defaults) so the controller's image-viewer
    sizing and FrameViewer construction do not receive None."""
    cam = MockCamera()
    assert cam.xsize is not None
    assert cam.ysize is not None
