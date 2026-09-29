"""
Variable snapshotting for ChronoPy tracer.

Uses delta encoding — only changed variables are stored per event.
Objects are represented as safe repr strings (never stored by reference
to avoid heap explosion).
"""

from __future__ import annotations

import reprlib
import sys
from typing import Any


# A repr that won't blow up on recursive structures
_safe_repr = reprlib.Repr()
_safe_repr.maxstring   = 200
_safe_repr.maxother    = 200
_safe_repr.maxlevel    = 4
_safe_repr.maxarray    = 8
_safe_repr.maxdict     = 8
_safe_repr.maxlist     = 8
_safe_repr.maxtuple    = 8
_safe_repr.maxset      = 8
_safe_repr.maxfrozenset = 8
_safe_repr.maxlong     = 80
_safe_repr.maxdeque    = 8


def safe_repr(obj: Any) -> str:
    """Return a repr string that is safe for any object."""
    try:
        return _safe_repr.repr(obj)
    except Exception:
        try:
            return f"<{type(obj).__name__} at 0x{id(obj):x}>"
        except Exception:
            return "<??>"


def safe_type(obj: Any) -> str:
    """Return the type name string safely."""
    try:
        return type(obj).__qualname__
    except Exception:
        return "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# Frame snapshot helpers
# ──────────────────────────────────────────────────────────────────────────────

# Variables that we skip (interpreter internals, our own tracer)
_SKIP_VARS = frozenset({
    "__builtins__", "__doc__", "__spec__", "__loader__",
    "__name__", "__package__", "__cached__", "__file__",
    # our tracer injects these
    "_chronopy_tracer",
})

# Blacklisted module prefixes (avoid tracing our own internals)
_SKIP_MODULES = ("chronopy.", "importlib.", "encodings.")


def should_trace_frame(frame) -> bool:
    """Return True if we should record this frame's variables."""
    filename = frame.f_code.co_filename
    if not filename or filename.startswith("<"):
        return False
    module = frame.f_globals.get("__name__", "")
    for prefix in _SKIP_MODULES:
        if module.startswith(prefix):
            return False
    return True


class FrameSnapshotter:
    """
    Tracks variable state for a single frame and computes deltas.

    prev_state: dict[name -> repr_string]  (last observed value)
    """

    __slots__ = ("_prev",)

    def __init__(self):
        self._prev: dict[str, str] = {}

    def snapshot(self, frame, full: bool = False) -> tuple[dict, dict | None]:
        """
        Compute a delta snapshot for the frame's locals.

        Returns:
            changed  — dict of {name: repr} for variables that changed
            full_locals — dict of all vars (only when full=True)
        """
        current: dict[str, str] = {}
        try:
            locs = frame.f_locals
        except Exception:
            return {}, None

        for name, val in locs.items():
            if name in _SKIP_VARS:
                continue
            if name.startswith("__") and name.endswith("__"):
                continue
            current[name] = safe_repr(val)

        changed = {}
        for name, repr_val in current.items():
            if self._prev.get(name) != repr_val:
                changed[name] = repr_val

        # Track deletions
        for name in list(self._prev.keys()):
            if name not in current:
                changed[name] = "<deleted>"

        self._prev = current
        full_locals = current if full else None
        return changed, full_locals
