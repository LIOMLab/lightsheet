"""IBeamSmartLaser — ``ILaser``-shaped adapter wrapping the existing,
rig-confirmed ``IBeam`` serial driver (Toptica iBeam Smart, COM4).

This is a **re-wrap, not a rewrite**: the inner ``IBeam`` engine
(``lightsheet/hal/real/ibeam.py``) and its reply-lag mitigations (per-instance
lock, 50 ms inter-command gap, input-buffer flush before every command) are
untouched. The adapter converts mW <-> µW, mirrors ``active`` / ``error`` /
``error_message`` from the inner engine, and exposes ``get_output_power()``
in mW for the GUI readback field.

**mW -> µW conversion (D-01):** ``set_power(mw)`` takes milliwatts; ``power``
/ ``max_power`` attrs are in mW. The adapter converts mW to µW (× 1000) and
delegates the actual serial round-trip to ``self._ibeam.set_power(uw)``.

**Two-layer clamp (AGENTS.md §2 — Class IIIB laser safety):**
1. ``set_power`` clamps ``mw`` to ``[0.0, max_power]`` (mW) at the adapter
   layer before converting to µW — the interface-layer clamp.
2. The inner ``IBeam.set_power`` clamps ``power_uw`` to
   ``[0, self._ibeam.max_power]`` (µW) independently — the native-unit
   clamp, independent of the mW clamp so a config typo in one unit cannot
   bypass the other layer.

**Lock identity (D-02):** ``self._lock`` IS ``self._ibeam._lock`` — the same
object, not a new lock. The daemon-thread write paths acquire
``self.lasers[i]._lock`` (the adapter's lock), and the inner ``_send_cmd``
acquires ``self._lock`` (the inner engine's lock); lock identity guarantees
they are the same lock so a daemon write holding the adapter lock excludes
a concurrent ``_send_cmd`` round-trip on the same engine.

**Synchronous ``off()`` (AGENTS.md §2 — E-stop kill path):** ``off()``
calls ``self._ibeam.off()``, sets ``active = False`` and ``power = 0.0``,
and returns ``None`` immediately — no thread/queue offload. The GUI-thread
E-stop handler calls this directly; offloading it would break the
synchronous-off safety contract.

**Error-surface mirroring:** ``on()`` mirrors ``active`` from the inner
``_is_on`` and ``error`` / ``error_message`` from the inner error surface,
so a firmware rejection (``%SYS-E``) leaves the adapter's ``active = False``
— the GUI never shows the laser as energized when the firmware refused.
``set_power`` guards the ``self.power`` mirror on the inner error surface
so a rejected write does not leave the adapter believing the commanded
power was applied. ``get_output_power()`` returns ``None`` on an inner
error so the GUI readback field can distinguish "no reading" from
"reading is 0".

The inner ``IBeam`` engine is constructed in ``__init__`` but NOT opened
(``IBeam.__init__`` does not call ``open()``); the controller's
``hardware_init`` is responsible for calling ``open()`` on the inner engine
(or the adapter may expose a passthrough — left to the controller rewrite).
"""

from lightsheet.hal.interfaces import ILaser
from lightsheet.hal.real.ibeam import IBeam


class IBeamSmartLaser(ILaser):
    """``ILaser`` adapter for the Toptica iBeam Smart (L2, COM4 serial).

    Wraps the existing rig-confirmed ``IBeam`` serial engine. mW -> µW
    (× 1000). ``off()`` is synchronous (E-stop kill path). ``_lock`` is the
    same object as the inner ``IBeam._lock`` (lock identity).
    """

    def __init__(self, label: str = "Laser 2 (640 nm)") -> None:
        # The inner rig-confirmed serial engine. __init__ does NOT open the
        # serial port — the controller's hardware_init is responsible for
        # calling open() (mirrors the existing IBeam construction pattern).
        self._ibeam = IBeam()

        # mW-canonical ILaser surface (D-01). The inner IBeam reports
        # wavelength in nm (640, serial self-report) and max_power in µW
        # (150000 = 150 mW, rig-confirmed + `show data` Pmax field); the
        # adapter converts max_power to mW for the interface.
        self.label = label
        self.wavelength = self._ibeam.wavelength  # 640 (nm)
        self.max_power = self._ibeam.max_power / 1000.0  # uW -> mW
        self.power = 0.0  # mW
        self.active = False
        self.error = 0
        self.error_message = ""

        # Lock identity (D-02): the adapter's lock IS the inner IBeam's
        # lock — the same object, not a new lock. The daemon-thread write
        # paths acquire self.lasers[i]._lock (the adapter's lock), and the
        # inner _send_cmd acquires self._lock (the inner engine's lock);
        # identity guarantees they are the same lock so a daemon write
        # holding the adapter lock excludes a concurrent _send_cmd
        # round-trip on the same engine.
        self._lock = self._ibeam._lock

    def on(self) -> None:
        """Energize the laser — delegates the serial round-trip to the inner
        ``IBeam.on()``, then mirrors ``active`` from the inner ``_is_on`` and
        ``error`` / ``error_message`` from the inner error surface. If the
        inner ``laser on`` was rejected (``%SYS-E``), the inner engine keeps
        ``_is_on = False`` and the adapter mirrors ``active = False`` so the
        GUI never shows the laser as energized when the firmware refused.
        """
        self._ibeam.on()
        self.active = self._ibeam._is_on
        self.error = self._ibeam.error
        self.error_message = self._ibeam.error_message

    def off(self) -> None:
        """Synchronous E-stop kill path (AGENTS.md §2).

        Calls ``self._ibeam.off()``, sets ``active = False`` and
        ``power = 0.0``, and returns ``None`` immediately — no thread/queue
        offload. The GUI-thread E-stop handler calls this directly;
        offloading it would break the synchronous-off safety contract for a
        Class IIIB laser.
        """
        self._ibeam.off()
        self.active = False
        self.power = 0.0

    def set_power(self, mw: float) -> None:
        """Set the staged laser power in milliwatts (mW canonical).

        Clamps ``mw`` to ``[0.0, max_power]`` (mW) at the adapter layer
        (first safety layer, AGENTS.md §2), converts to µW (× 1000), and
        delegates the serial round-trip to ``self._ibeam.set_power(uw)``.
        The inner ``IBeam.set_power`` clamps the µW value to its own
        ``max_power`` independently (second safety layer). On a firmware
        rejection (inner ``error != 0``) the adapter MUST NOT update
        ``self.power`` — the inner engine already guards its own ``_power``
        on the error surface, and the adapter mirrors that guard on the mW
        side so a failed write does not leave the adapter believing the
        commanded power was applied.
        """
        mw = max(0.0, min(mw, self.max_power))
        self._ibeam.set_power(int(mw * 1000))  # mW -> uW; inner clamp still applies
        if not self._ibeam.error:
            self.power = mw

    def get_output_power(self) -> float | None:
        """Read the current channel output power in milliwatts (mW).

        Delegates the serial round-trip to the inner
        ``IBeam.get_output_power()`` (which returns µW and already filters
        the multi-channel ``show level power`` reply by ``CH{channel}`` —
        the adapter does NOT re-implement that parse). Returns the µW value
        divided by 1000.0 (mW), or ``None`` on an inner error (parse
        failure / firmware rejection) so the GUI readback field can
        distinguish "no reading" from "reading is 0".
        """
        uw = self._ibeam.get_output_power()
        if self._ibeam.error:
            return None
        return uw / 1000.0
