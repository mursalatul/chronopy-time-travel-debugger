"""
Event model for ChronoPy tracer.

Each event represents one observable action during program execution:
a line execution, function call/return, exception, or variable mutation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional


class EventKind(IntEnum):
    """Type of execution event."""
    LINE        = 1   # A source line was executed
    CALL        = 2   # A function was called
    RETURN      = 3   # A function returned
    EXCEPTION   = 4   # An exception was raised
    VAR_CHANGE  = 5   # A variable changed value (synthetic, detected at LINE)
    C_CALL      = 6   # A C extension function was called
    C_RETURN    = 7   # A C extension function returned


@dataclass
class FrameInfo:
    """Snapshot of a frame's identity."""
    func_name: str
    filename: str
    lineno: int
    # Unique id stable across the trace (frame object id)
    frame_id: int

    def to_dict(self) -> dict:
        return {
            "func_name": self.func_name,
            "filename":  self.filename,
            "lineno":    self.lineno,
            "frame_id":  self.frame_id,
        }


@dataclass
class VarSnapshot:
    """
    A compact snapshot of local + global variables at an event.

    We store only *changed* variables (delta encoding) to keep the log small.
    full_locals is only set on CALL events (first appearance of a frame).
    """
    changed: dict[str, Any] = field(default_factory=dict)  # name -> repr-string
    full_locals: Optional[dict[str, Any]] = None            # on CALL events


@dataclass
class Event:
    """
    One recorded event in the execution timeline.

    step_index is the global monotonic counter across the entire trace.
    """
    step_index: int
    kind: EventKind
    timestamp: float           # time.perf_counter() at recording
    frame: FrameInfo
    lineno: int                # effective line (may differ from frame.lineno)
    return_value: Any = None   # populated for RETURN events
    exception: Any = None      # populated for EXCEPTION events
    vars: Optional[VarSnapshot] = None

    # Call-graph linkage
    parent_step: Optional[int] = None   # step_index of the matching CALL
    depth: int = 0                      # call depth at this point

    def to_dict(self) -> dict:
        d = {
            "step_index":   self.step_index,
            "kind":         self.kind.name,
            "kind_id":      int(self.kind),
            "timestamp":    self.timestamp,
            "frame":        self.frame.to_dict(),
            "lineno":       self.lineno,
            "depth":        self.depth,
        }
        if self.return_value is not None:
            d["return_value"] = self.return_value
        if self.exception is not None:
            d["exception"] = self.exception
        if self.vars:
            d["vars_changed"] = self.vars.changed
            if self.vars.full_locals:
                d["vars_full"] = self.vars.full_locals
        if self.parent_step is not None:
            d["parent_step"] = self.parent_step
        return d
