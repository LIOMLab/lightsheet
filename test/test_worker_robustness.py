'''
Static-source regression tests for the acquisition-worker robustness fixes.

Controller_MainWindow cannot be instantiated headless on this Mac (no PyQt5
display, no hardware SDKs), so these tests follow the test_estop.py pattern:
they read gui/controller.py as text, slice out individual method bodies with
regex, and assert the safety-critical structural properties hold. This guards
against regressions where the fixes are accidentally removed or weakened.

Covered fixes:
  1. Stop Stack Mode no longer joins the worker thread on the GUI thread
     (the GUI-freeze fix).
  2. single_mode_worker, stack_mode_worker, live_mode_worker, and
     preview_mode_worker wrap their bodies in try/finally so the finished
     signal always fires exactly once.
  3. acquire_scan disarms the camera on its timeout-return path.
  4. closeEvent joins worker threads with a bounded timeout instead of an
     unconditional fixed sleep.
  5. start_lasers() reads self.lasers.error after laser1_on() and surfaces
     a DAQ AO write failure to the operator instead of silently no-op'ing.
  6. The four acquisition workers have an except clause before their finally
     that emits a cause message via sig_message, so an unhandled exception
     is reported to the operator instead of dying silently to stderr.
'''

import os
import re
import sys
sys.path.append("")

_CONTROLLER_SRC = os.path.join(os.path.dirname(__file__), '..', 'gui', 'controller.py')


def _read_controller_source():
    with open(_CONTROLLER_SRC, 'r') as f:
        return f.read()


def _slice_method(src, name):
    """Return the body of `def <name>(self, ...):` up to the next top-level
    def or @pyqtSlot decorator. Includes the def line itself. Accepts any
    parameter list (most workers take only self; closeEvent takes event)."""
    m = re.search(r'def ' + re.escape(name) + r'\(self[^)]*\):', src)
    assert m, f"{name} is missing from gui/controller.py"
    body = src[m.start():]
    end = re.search(r'\n    def |\n    @pyqtSlot', body[1:])
    if end:
        body = body[:end.start() + 1]
    return body


# --------------------------------------------------------------------------- #
# Test 1: the stop branch of updateUi_stack_mode_button must not join the
# worker thread on the GUI thread (the GUI-freeze fix).
# --------------------------------------------------------------------------- #
def test_stack_mode_stop_branch_does_not_join():
    """The stop branch (between `if self.stack_mode_started:` and the
    following `else:`) must not call .join() — joining blocks the Qt event
    loop for the remainder of whatever blocking hardware call the worker is
    currently inside, freezing the GUI."""
    src = _read_controller_source()
    body = _slice_method(src, 'updateUi_stack_mode_button')
    # Isolate the stop branch: from `if self.stack_mode_started:` to `else:`.
    start_m = re.search(r'if self\.stack_mode_started:', body)
    assert start_m, "stack_mode_started if-branch missing"
    else_m = re.search(r'\n        else:', body[start_m.end():])
    assert else_m, "stack_mode_started else-branch missing"
    stop_branch = body[start_m.start():start_m.end() + else_m.start()]
    assert '.join()' not in stop_branch, (
        "Stop Stack Mode branch must not call .join() on the GUI thread — "
        "it blocks the Qt event loop and freezes the GUI")


# --------------------------------------------------------------------------- #
# Test 2: single_mode_worker and stack_mode_worker must wrap their bodies in
# try/finally with the finished signal in the finally clause.
# --------------------------------------------------------------------------- #
def test_workers_have_try_finally_with_finished_signal():
    """Each worker body must contain exactly one `finally:` block, and the
    corresponding sig_*_mode_finished.emit() call must appear AFTER the
    `finally:` keyword (string-index comparison) so the signal fires exactly
    once whether the method returns early, completes normally, or raises.

    Covers single_mode_worker, stack_mode_worker, live_mode_worker, and
    preview_mode_worker — all four acquisition workers must follow the same
    try/finally + finished-signal pattern so an exception in any of them
    re-enables the UI instead of leaving it stuck on 'Stop <Mode>'."""
    src = _read_controller_source()
    workers = {
        'single_mode_worker': 'self.sig_single_mode_finished.emit()',
        'stack_mode_worker': 'self.sig_stack_mode_finished.emit()',
        'live_mode_worker': 'self.sig_live_mode_finished.emit()',
        'preview_mode_worker': 'self.sig_preview_mode_finished.emit()',
    }
    for worker, emit_call in workers.items():
        body = _slice_method(src, worker)
        finally_count = body.count('finally:')
        assert finally_count == 1, (
            f"{worker} must contain exactly one finally: block, found "
            f"{finally_count}")
        finally_idx = body.index('finally:')
        emit_idx = body.index(emit_call)
        assert emit_idx > finally_idx, (
            f"{worker}: {emit_call} must appear after the finally: keyword "
            f"(emit at index {emit_idx}, finally at {finally_idx}) so it "
            f"fires even when an exception propagates from cleanup")


# --------------------------------------------------------------------------- #
# Test 3: acquire_scan must disarm the camera on its timeout-return path.
# --------------------------------------------------------------------------- #
def test_acquire_scan_disarms_on_timeout():
    """The timeout-return path (the block starting at
    `if self.camera.recorder_timeout_status:`) must call self.camera.disarm()
    before the following top-level `return`, so a camera left mid-timeout is
    always disarmed before any worker that might die afterward skips its own
    cleanup."""
    src = _read_controller_source()
    body = _slice_method(src, 'acquire_scan')
    timeout_check = 'if self.camera.recorder_timeout_status:'
    check_idx = body.find(timeout_check)
    assert check_idx != -1, (
        "acquire_scan missing `if self.camera.recorder_timeout_status:` "
        "timeout check")
    # Find the next top-level `return` after the timeout check (a return
    # at column 12, i.e. 3 levels of indent: method + if-block).
    after_check = body[check_idx:]
    return_m = re.search(r'\n            return\b', after_check)
    assert return_m, (
        "acquire_scan timeout block missing its return statement")
    timeout_block = after_check[:return_m.start() + return_m.end()]
    assert 'self.camera.disarm()' in timeout_block, (
        "acquire_scan timeout-return path must call self.camera.disarm() "
        "before returning so the camera is not left armed")


# --------------------------------------------------------------------------- #
# Test 5: start_lasers() must read self.lasers.error after laser1_on() and
# surface a DAQ AO write failure to the operator.
# --------------------------------------------------------------------------- #
def test_start_lasers_checks_laser1_error():
    """start_lasers() calls self.lasers.laser1_on() but must then read
    self.lasers.error and emit an operator message via sig_message if the
    DAQ AO write failed. Lasers._update_setpoints catches the DAQ write
    failure on /Dev7/ao0:1, sets self.error = 1, reverts laser1_active =
    False, and deliberately does NOT raise (hardware-absence tolerance).
    Every other laser-1 call site surfaces that flag; start_lasers() is the
    only one that did not, so a failed laser-1 start during acquisition was
    a silent no-op — the operator saw nothing and the PSU stayed dark."""
    src = _read_controller_source()
    body = _slice_method(src, 'start_lasers')
    on_idx = body.find('self.lasers.laser1_on()')
    assert on_idx != -1, "start_lasers missing self.lasers.laser1_on()"
    err_check = 'if self.lasers.error:'
    err_idx = body.find(err_check, on_idx)
    assert err_idx != -1, (
        "start_lasers must check self.lasers.error after laser1_on() so a "
        "failed DAQ AO write is surfaced to the operator instead of a "
        "silent no-op")
    emit_call = 'self.sig_message.emit('
    emit_idx = body.find(emit_call, err_idx)
    assert emit_idx != -1, (
        "start_lasers must emit an operator message via sig_message when "
        "self.lasers.error is set after laser1_on()")
    reset = 'self.lasers.error = 0'
    reset_idx = body.find(reset, emit_idx)
    assert reset_idx != -1, (
        "start_lasers must reset self.lasers.error = 0 after emitting so a "
        "stale error flag does not re-fire on the next write")


# --------------------------------------------------------------------------- #
# Test 6: the four acquisition workers must have an except clause before
# their finally that emits a cause message via sig_message.
# --------------------------------------------------------------------------- #
def test_workers_have_except_clause_emitting_message():
    """Each acquisition worker is try/finally with the finished signal in
    finally. Without an except clause, an unhandled exception in the worker
    body is swallowed by the default threading excepthook: finally emits the
    finished signal (button reverts, looks stopped) but the operator is
    never told anything went wrong. Each worker must have exactly one
    `except Exception as e:` between the try body and the finally, emitting
    a cause message via sig_message BEFORE the finished signal so the
    operator sees the cause next to the mode-stopped notice. No bare
    `except:` may be present — it would re-introduce the silent-swallow
    defect."""
    src = _read_controller_source()
    workers = ['preview_mode_worker', 'live_mode_worker',
               'single_mode_worker', 'stack_mode_worker']
    for worker in workers:
        body = _slice_method(src, worker)
        except_count = body.count('except Exception as e:')
        assert except_count == 1, (
            f"{worker} must contain exactly one `except Exception as e:` "
            f"clause, found {except_count}")
        except_idx = body.index('except Exception as e:')
        emit_idx = body.find('self.sig_message.emit(', except_idx)
        assert emit_idx != -1, (
            f"{worker}: except clause must emit a cause message via "
            f"sig_message so the operator is told what went wrong")
        finally_idx = body.index('finally:')
        assert except_idx < finally_idx, (
            f"{worker}: except clause must precede finally so the message "
            f"is emitted before the finished signal")
        # No bare except: — it would swallow and re-introduce silent death.
        assert not re.search(r'\n\s+except:', body), (
            f"{worker}: a bare `except:` would silently swallow exceptions "
            f"and re-introduce the defect this test guards against")


# --------------------------------------------------------------------------- #
# Test 4: closeEvent must use a bounded thread join, not an unconditional
# fixed sleep.
# --------------------------------------------------------------------------- #
def test_closeEvent_uses_bounded_join_not_sleep():
    """closeEvent must not contain time.sleep(1) and must contain
    .join(timeout= so a stuck worker cannot hang application shutdown."""
    src = _read_controller_source()
    body = _slice_method(src, 'closeEvent')
    assert 'time.sleep(1)' not in body, (
        "closeEvent must not use time.sleep(1) — it hangs shutdown when a "
        "worker is stuck inside a long blocking hardware call")
    assert '.join(timeout=' in body, (
        "closeEvent must join worker threads with .join(timeout= so "
        "shutdown is bounded")
