"""
ChronoPy Core Tracer — uses sys.monitoring (PEP 669, Python 3.12+).

sys.monitoring provides low-overhead event hooks compared to sys.settrace.
We register for LINE, CALL, RETURN, and EXCEPTION events.
"""

from __future__ import annotations

import sys
import time
import threading
import runpy
from pathlib import Path
from typing import Any, Callable

from .events import Event, EventKind, FrameInfo, VarSnapshot
from .snapshot import FrameSnapshotter, should_trace_frame, safe_repr
from .store import TraceStore

if sys.version_info < (3, 12):
    raise RuntimeError("ChronoPy requires Python 3.12+ for sys.monitoring support.")


# Use a dedicated tool ID so we don't clash with other tools (e.g. coverage)
_TOOL_ID = sys.monitoring.DEBUGGER_ID


class Tracer:
    """
    Records a Python program's execution to a TraceStore.

    Usage:
        tracer = Tracer()
        with tracer:
            exec(some_code)
        store = tracer.store
    """

    def __init__(
        self,
        target_file: str | None = None,
        max_events: int = 500_000,
        capture_globals: bool = False,
    ):
        self.target_file  = str(Path(target_file).resolve()) if target_file else None
        self.max_events   = max_events
        self.capture_globals = capture_globals

        self.store = TraceStore()

        self._step        = 0
        self._depth       = 0
        self._active      = False
        self._lock        = threading.Lock()

        # Per-frame snapshotters keyed by frame id
        self._snapshots:  dict[int, FrameSnapshotter] = {}
        # Call stack: list of step_index for open CALL events
        self._call_stack: list[int] = []

        # Track start time for timestamps
        self._t0: float = 0.0

    # ──────────────────────────────────────────────────────────────────────────
    # Context manager
    # ──────────────────────────────────────────────────────────────────────────

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()

    # ──────────────────────────────────────────────────────────────────────────
    # Start / Stop
    # ──────────────────────────────────────────────────────────────────────────

    def start(self):
        """Activate sys.monitoring hooks."""
        if self._active:
            return
        self._active = True
        self._t0 = time.perf_counter()

        sys.monitoring.use_tool_id(_TOOL_ID, "chronopy")

        events = (
            sys.monitoring.events.PY_START
            | sys.monitoring.events.PY_RETURN
            | sys.monitoring.events.PY_RESUME   # covers line-level granularity via RESUME
            | sys.monitoring.events.LINE
            | sys.monitoring.events.RAISE
            | sys.monitoring.events.PY_THROW
        )
        sys.monitoring.set_events(_TOOL_ID, events)

        sys.monitoring.register_callback(_TOOL_ID, sys.monitoring.events.PY_START,    self._on_call)
        sys.monitoring.register_callback(_TOOL_ID, sys.monitoring.events.PY_RETURN,   self._on_return)
        sys.monitoring.register_callback(_TOOL_ID, sys.monitoring.events.LINE,        self._on_line)
        sys.monitoring.register_callback(_TOOL_ID, sys.monitoring.events.RAISE,       self._on_exception)
        sys.monitoring.register_callback(_TOOL_ID, sys.monitoring.events.PY_THROW,    self._on_exception)

    def stop(self):
        """Deactivate sys.monitoring hooks."""
        if not self._active:
            return
        self._active = False
        try:
            sys.monitoring.set_events(_TOOL_ID, sys.monitoring.events.NO_EVENTS)
            sys.monitoring.register_callback(_TOOL_ID, sys.monitoring.events.PY_START,  None)
            sys.monitoring.register_callback(_TOOL_ID, sys.monitoring.events.PY_RETURN, None)
            sys.monitoring.register_callback(_TOOL_ID, sys.monitoring.events.LINE,      None)
            sys.monitoring.register_callback(_TOOL_ID, sys.monitoring.events.RAISE,     None)
            sys.monitoring.register_callback(_TOOL_ID, sys.monitoring.events.PY_THROW,  None)
            sys.monitoring.free_tool_id(_TOOL_ID)
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _should_record(self, code) -> bool:
        """Filter: only record events from the target file (if set)."""
        if not self._active:
            return False
        if self._step >= self.max_events:
            return False
        filename = code.co_filename
        if not filename or filename.startswith("<"):
            return False
        if self.target_file and not filename.endswith(
            self.target_file.lstrip("/")[-60:]
        ):
            return False
        return True

    def _make_frame_info(self, code, lineno: int) -> FrameInfo:
        return FrameInfo(
            func_name=code.co_qualname,
            filename=code.co_filename,
            lineno=lineno,
            frame_id=id(code),
        )

    def _next_step(self) -> int:
        with self._lock:
            idx = self._step
            self._step += 1
            return idx

    def _ts(self) -> float:
        return time.perf_counter() - self._t0

    # ──────────────────────────────────────────────────────────────────────────
    # sys.monitoring callbacks
    # ──────────────────────────────────────────────────────────────────────────

    def _on_call(self, code, instruction_offset: int):
        """Fires when a Python function call begins."""
        if not self._should_record(code):
            return sys.monitoring.DISABLE
        try:
            frame_info = self._make_frame_info(code, code.co_firstlineno)
            parent = self._call_stack[-1] if self._call_stack else None
            step_idx = self._next_step()
            self._depth += 1
            self._call_stack.append(step_idx)

            # Initialize per-frame snapshot tracker
            fid = id(code)
            if fid not in self._snapshots:
                self._snapshots[fid] = FrameSnapshotter()

            event = Event(
                step_index=step_idx,
                kind=EventKind.CALL,
                timestamp=self._ts(),
                frame=frame_info,
                lineno=code.co_firstlineno,
                depth=self._depth,
                parent_step=parent,
            )
            self.store.append(event)
        except Exception:
            pass

    def _on_return(self, code, instruction_offset: int, retval: Any):
        """Fires when a Python function returns."""
        if not self._should_record(code):
            return
        try:
            frame_info = self._make_frame_info(code, code.co_firstlineno)
            parent = self._call_stack.pop() if self._call_stack else None
            step_idx = self._next_step()
            depth = self._depth
            self._depth = max(0, self._depth - 1)

            event = Event(
                step_index=step_idx,
                kind=EventKind.RETURN,
                timestamp=self._ts(),
                frame=frame_info,
                lineno=code.co_firstlineno,
                return_value=safe_repr(retval),
                depth=depth,
                parent_step=parent,
            )
            self.store.append(event)
        except Exception:
            pass

    def _on_line(self, code, line_number: int):
        """Fires for each source line executed."""
        if not self._should_record(code):
            return sys.monitoring.DISABLE
        try:
            frame_info = self._make_frame_info(code, line_number)
            step_idx = self._next_step()

            # Try to get variable delta — requires current frame
            # sys.monitoring LINE callback does NOT pass the frame object.
            # We use code + lineno only; variable capture happens via
            # a lightweight sys.settrace companion running only on target files.
            event = Event(
                step_index=step_idx,
                kind=EventKind.LINE,
                timestamp=self._ts(),
                frame=frame_info,
                lineno=line_number,
                depth=self._depth,
                parent_step=self._call_stack[-1] if self._call_stack else None,
            )
            self.store.append(event)
        except Exception:
            pass

    def _on_exception(self, code, instruction_offset: int, exception: BaseException):
        """Fires when an exception is raised."""
        if not self._should_record(code):
            return
        try:
            frame_info = self._make_frame_info(code, code.co_firstlineno)
            step_idx = self._next_step()

            event = Event(
                step_index=step_idx,
                kind=EventKind.EXCEPTION,
                timestamp=self._ts(),
                frame=frame_info,
                lineno=code.co_firstlineno,
                exception=f"{type(exception).__name__}: {exception}",
                depth=self._depth,
                parent_step=self._call_stack[-1] if self._call_stack else None,
            )
            self.store.append(event)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Hybrid Tracer: sys.monitoring + sys.settrace companion for variable capture
# ──────────────────────────────────────────────────────────────────────────────

class HybridTracer(Tracer):
    """
    Extends Tracer with a sys.settrace companion that captures local variable
    snapshots at each LINE event, using delta encoding.

    sys.monitoring handles the fast path; sys.settrace is only activated for
    the target file to minimise overhead.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._frame_snaps: dict[int, FrameSnapshotter] = {}

    def start(self):
        super().start()
        sys.settrace(self._settrace_handler)

    def stop(self):
        sys.settrace(None)
        super().stop()

    def _settrace_handler(self, frame, event, arg):
        """sys.settrace companion — captures variables, then delegates to monitoring."""
        if not self._active:
            return None

        filename = frame.f_code.co_filename
        if not filename or filename.startswith("<"):
            return self._settrace_handler

        if self.target_file and self.target_file not in filename:
            return self._settrace_handler

        fid = id(frame)
        if fid not in self._frame_snaps:
            self._frame_snaps[fid] = FrameSnapshotter()

        snapper = self._frame_snaps[fid]

        if event == "call":
            changed, full = snapper.snapshot(frame, full=True)
        elif event in ("line", "return"):
            changed, full = snapper.snapshot(frame, full=False)
        elif event == "exception":
            changed, full = {}, None
        else:
            return self._settrace_handler

        # Attach the var snapshot to the most recently appended event
        # that matches this frame + lineno
        if changed or full:
            var_snap = VarSnapshot(changed=changed, full_locals=full)
            self.store.attach_vars_to_last(
                filename=filename,
                lineno=frame.f_lineno,
                vars=var_snap,
            )

        return self._settrace_handler


def run_file(path: str, tracer: Tracer | None = None) -> Tracer:
    """
    Run a Python file under the tracer and return the completed tracer.

    If tracer is None, a HybridTracer is created automatically.
    """
    path = str(Path(path).resolve())
    if tracer is None:
        tracer = HybridTracer(target_file=path)

    with tracer:
        try:
            runpy.run_path(path, run_name="__main__")
        except SystemExit:
            pass
        except Exception as exc:
            # Still record — the trace up to the crash is valuable
            pass

    return tracer
