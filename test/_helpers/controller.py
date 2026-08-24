"""Extracted, VERBATIM ``_load_method`` / ``_slice_method`` controller-testing
mechanism (AGENTS.md §5).

This is the single canonical import path for the sanctioned controller-method
testing pattern: extract the REAL method body from a ``lightsheet/gui/*.py``
source file and ``exec`` it in a controlled namespace, then call the resulting
function against a minimal ``Mock`` stand-in ``self``. This runs the same code
that runs on the rig — proving runtime behavior, NOT a string match on the
source. See AGENTS.md §5: never write static-source grep tests; exercise the
real method via exec of its extracted body when the class cannot be
instantiated.

The mechanism was previously triplicated across ``test/test_laser_controls.py``,
``test/test_controller_behavior.py``, and ``test/test_demo_factory.py``. This
module is the one shared copy; those files now import from here.

The path constants point at the production GUI source files. This module lives
one directory deeper than the test files (``test/_helpers/`` vs ``test/``), so
the ``os.path.join`` chain uses one more ``..`` segment than the per-file
constants it replaces.
"""

import datetime
import logging
import os
import re
from collections.abc import Callable
from typing import Any

_CONTROLLER_SRC = os.path.join(
    os.path.dirname(__file__), "..", "..", "lightsheet", "gui", "controller.py"
)
_HW_SRC = os.path.join(
    os.path.dirname(__file__), "..", "..", "lightsheet", "gui", "hardware_manager.py"
)
_ACQ_SRC = os.path.join(
    os.path.dirname(__file__), "..", "..", "lightsheet", "gui", "acquisition_coordinator.py"
)
_FS_SRC = os.path.join(
    os.path.dirname(__file__), "..", "..", "lightsheet", "gui", "frame_saver_controller.py"
)
_MC_SRC = os.path.join(
    os.path.dirname(__file__), "..", "..", "lightsheet", "gui", "motor_controller.py"
)
_MAIN_SRC = os.path.join(
    os.path.dirname(__file__), "..", "..", "lightsheet", "__main__.py"
)


def _slice_method(src: str, method_sig: str) -> str:
    """Return the body of a method, from its `def <sig>:` line up to the
    next top-level def/@pyqtSlot decorator."""
    m = re.search(r"def " + re.escape(method_sig) + r":", src)
    assert m, f"{method_sig} is missing"
    body = src[m.start() :]
    end = re.search(r"\n    def |\n    @pyqtSlot", body[1:])
    if end:
        body = body[: end.start() + 1]
    return body


def _load_method(
    method_sig: str,
    extra_globals: dict[str, Any] | None = None,
    src_path: str = _CONTROLLER_SRC,
) -> Callable[..., Any]:
    """Extract a method body from the given source file and return a callable
    that executes the real source. Defaults to controller.py; pass `_HW_SRC`
    for methods moved to HardwareManager. `extra_globals` seeds the exec
    namespace with module-level names the body references (datetime, logging,
    logger, ...). `logger` is the module-level logger the source declares;
    seeding it here lets the migrated logger.* calls resolve when the body
    is exec'd in isolation."""
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    body = _slice_method(src, method_sig)
    namespace = {
        "datetime": datetime,
        "logging": logging,
        "logger": logging.getLogger("test_controller_behavior"),
    }
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(body, src_path, "exec"), namespace)
    func_name = method_sig.split("(")[0].strip()
    return namespace[func_name]
