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
  7. start_lasers()/stop_lasers() read only cached auto-laser bools
     (self._auto_laser1 / self._auto_laser2) sampled on the GUI thread by
     _cache_auto_laser_flags() before the worker is spawned — no acquisition
     worker reads a Qt widget directly (AGENTS.md §11 hard rule).
  8. acquire_scan surfaces self.siggen.error after create_scanner() and
     returns before the camera recorder is primed, so a DAQ scan-task
     creation failure is reported to the operator instead of presenting as
     a silent 15 s camera recorder timeout; stack_mode_worker breaks the
     stack loop on the first such failure instead of repeating it per plane.
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


# --------------------------------------------------------------------------- #
# Test 7: start_lasers()/stop_lasers() must read only cached auto-laser bools
# sampled on the GUI thread — no acquisition worker may read a Qt widget
# directly (AGENTS.md §11 hard rule).
# --------------------------------------------------------------------------- #
def test_start_lasers_uses_cached_auto_flags():
    """The auto-laser checkbox states must be sampled on the GUI thread by
    _cache_auto_laser_flags() before any acquisition worker is spawned, and
    the workers (which call start_lasers()/stop_lasers() off the GUI thread)
    must read only the cached bools self._auto_laser1 / self._auto_laser2.

    Reading a Qt widget from a non-GUI thread is undefined behaviour per
    Qt's threading model (AGENTS.md §11) and can stall or kill the worker
    mid-acquisition — between camera.arm_scan() and the DAQ scanner task
    creation — leaving the camera armed and recording while the scanner
    tasks are never created, which presents as a silent 15 s camera
    recorder timeout with no error. The fix is structural: the only
    widget reads in the file live inside the single GUI-thread helper,
    invoked at every entry point that leads to a worker calling
    start_lasers()/stop_lasers()."""
    src = _read_controller_source()

    # The two checkbox object names may appear in exactly one place each —
    # inside _cache_auto_laser_flags — proving no worker-reachable code
    # reads a widget.
    assert src.count('checkBox_laserOneAutomatic') == 1, (
        "checkBox_laserOneAutomatic must be read in exactly one place "
        "(_cache_auto_laser_flags); a second occurrence means a worker "
        "thread is reading a Qt widget directly (AGENTS.md §11 violation)")
    assert src.count('checkBox_laserTwoAutomatic') == 1, (
        "checkBox_laserTwoAutomatic must be read in exactly one place "
        "(_cache_auto_laser_flags); a second occurrence means a worker "
        "thread is reading a Qt widget directly (AGENTS.md §11 violation)")

    cache_body = _slice_method(src, '_cache_auto_laser_flags')
    assert 'checkBox_laserOneAutomatic' in cache_body, (
        "checkBox_laserOneAutomatic must be read inside "
        "_cache_auto_laser_flags")
    assert 'checkBox_laserTwoAutomatic' in cache_body, (
        "checkBox_laserTwoAutomatic must be read inside "
        "_cache_auto_laser_flags")

    # start_lasers and stop_lasers read only the cached bools.
    for name in ('start_lasers', 'stop_lasers'):
        body = _slice_method(src, name)
        assert 'self._auto_laser1' in body, (
            f"{name} must read self._auto_laser1 (the cached flag), not "
            f"the Qt widget directly")
        assert 'self._auto_laser2' in body, (
            f"{name} must read self._auto_laser2 (the cached flag), not "
            f"the Qt widget directly")
        assert 'checkBox_laserOneAutomatic' not in body, (
            f"{name} must not read checkBox_laserOneAutomatic directly — "
            f"it is a worker-thread method and Qt widgets belong to the "
            f"GUI thread (AGENTS.md §11)")
        assert 'checkBox_laserTwoAutomatic' not in body, (
            f"{name} must not read checkBox_laserTwoAutomatic directly — "
            f"it is a worker-thread method and Qt widgets belong to the "
            f"GUI thread (AGENTS.md §11)")

    # _cache_auto_laser_flags() is invoked at exactly four GUI-thread sites:
    # close_modes (which calls stop_lasers) and the three mode-button
    # handlers that spawn a worker.
    assert src.count('self._cache_auto_laser_flags()') == 4, (
        "_cache_auto_laser_flags() must be called at exactly four sites "
        "(close_modes + the three mode-button handlers); fewer means a "
        "worker can act on a stale flag value")
    for name in ('close_modes', 'updateUi_live_mode_button',
                 'updateUi_single_mode_button',
                 'updateUi_stack_mode_button'):
        body = _slice_method(src, name)
        assert 'self._cache_auto_laser_flags()' in body, (
            f"{name} must call self._cache_auto_laser_flags() before "
            f"spawning a worker / calling stop_lasers so the worker reads "
            f"current checkbox states, not stale ones")


# --------------------------------------------------------------------------- #
# Test 8: acquire_scan must surface self.siggen.error after create_scanner()
# and return before the camera recorder is primed; stack_mode_worker must
# break the stack loop on the first scan-task failure.
# --------------------------------------------------------------------------- #
def test_acquire_scan_surfaces_siggen_error():
    """create_scanner() (src/siggen.py) wraps its DAQ task creation in a
    bare except that sets self.siggen.error = 1 and a generic
    'create_scan error' message but never raises. Without a check in
    acquire_scan, a failed create_scanner() leaves task_galvo_etl /
    task_camera as None, start_scanner() / monitor_scanner() become
    no-ops, and the camera waits out its full recorder timeout with
    nothing to report — a silent 15 s timeout that is impossible to
    diagnose. acquire_scan must clear the stale flag before
    create_scanner(), check it immediately after, emit an operator
    message via sig_message, tear down the scanner and disarm the camera,
    and return BEFORE start_recorder() primes the recorder. The stack
    worker must then break the loop so the same failure is not repeated
    once per remaining plane."""
    src = _read_controller_source()
    body = _slice_method(src, 'acquire_scan')

    create_idx = body.find('self.siggen.create_scanner()')
    assert create_idx != -1, "acquire_scan missing self.siggen.create_scanner()"

    # Stale-state reset must precede create_scanner() so the post-check
    # reflects this call only.
    reset_idx = body.find('self.siggen.error = 0')
    assert reset_idx != -1 and reset_idx < create_idx, (
        "acquire_scan must reset self.siggen.error = 0 BEFORE "
        "create_scanner() so a stale error from a prior acquisition does "
        "not trip the post-check")

    # The error check must gate the recorder: it must appear after
    # create_scanner() and before start_recorder().
    err_check = 'if self.siggen.error:'
    err_idx = body.find(err_check, create_idx)
    assert err_idx != -1, (
        "acquire_scan must check `if self.siggen.error:` after "
        "create_scanner() so a DAQ scan-task creation failure is surfaced")
    recorder_idx = body.find('self.camera.start_recorder(', create_idx)
    assert recorder_idx != -1, (
        "acquire_scan missing self.camera.start_recorder(")
    assert err_idx < recorder_idx, (
        "acquire_scan: the `if self.siggen.error:` check must appear "
        "BEFORE self.camera.start_recorder() so a scan-task failure "
        "aborts before the recorder is primed (otherwise the camera "
        "still waits out its full timeout)")

    # The error block must emit an operator message and return.
    block_end = body.find('\n        ', err_idx + len(err_check))
    # Find the return at the method's if-block indent (8 spaces).
    return_m = re.search(r'\n            return\b', body[err_idx:])
    assert return_m, (
        "acquire_scan siggen.error block must return so the recorder is "
        "never primed after a scan-task creation failure")
    err_block = body[err_idx:err_idx + return_m.end()]
    assert 'self.sig_message.emit(' in err_block, (
        "acquire_scan siggen.error block must emit an operator message "
        "via sig_message so the DAQ failure is reported, not silent")
    assert 'self.siggen.delete_scanner()' in err_block, (
        "acquire_scan siggen.error block must delete the scanner so the "
        "DAQ hardware is left in a consistent state")
    assert 'self.camera.disarm()' in err_block, (
        "acquire_scan siggen.error block must disarm the camera so it is "
        "not left armed after the abort")

    # stack_mode_worker must break the stack loop on the first scan-task
    # failure so the same failure is not repeated once per remaining plane.
    stack_body = _slice_method(src, 'stack_mode_worker')
    stack_err_idx = stack_body.find('if self.siggen.error:')
    assert stack_err_idx != -1, (
        "stack_mode_worker must check `if self.siggen.error:` so a DAQ "
        "scan-task failure aborts the stack instead of recurring per plane")
    break_idx = stack_body.find('break', stack_err_idx)
    assert break_idx != -1, (
        "stack_mode_worker must break the stack loop when "
        "self.siggen.error is set after acquire_scan")
