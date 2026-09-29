"""
ReplayEngine — step-forward and step-backward through a TraceStore.

The engine maintains a cursor (current_step) and exposes:
  • step_forward()   — advance by N steps
  • step_backward()  — rewind by N steps
  • jump_to(step)    — teleport to any step
  • current_state()  — reconstruct variable state at cursor
  • search(*)        — find next/prev event matching criteria
"""

from __future__ import annotations

from typing import Any, Optional

from chronopy.tracer.store import TraceStore
from chronopy.tracer.events import Event, EventKind


class ReplayEngine:
    """Stateful cursor over a TraceStore enabling time-travel."""

    def __init__(self, store: TraceStore):
        self.store = store
        self._cursor: int = 0
        self._state_cache: dict[int, dict[str, str]] = {}

    # ──────────────────────────────────────────────────────────────────────────
    # Cursor movement
    # ──────────────────────────────────────────────────────────────────────────

    @property
    def cursor(self) -> int:
        return self._cursor

    @property
    def total(self) -> int:
        return len(self.store)

    def jump_to(self, step: int) -> Event | None:
        step = max(0, min(step, self.total - 1))
        self._cursor = step
        return self.store.get(step)

    def step_forward(self, n: int = 1) -> Event | None:
        return self.jump_to(self._cursor + n)

    def step_backward(self, n: int = 1) -> Event | None:
        return self.jump_to(self._cursor - n)

    def current_event(self) -> Event | None:
        return self.store.get(self._cursor)

    # ──────────────────────────────────────────────────────────────────────────
    # State reconstruction
    # ──────────────────────────────────────────────────────────────────────────

    def current_state(self, filename: str | None = None, func_name: str | None = None) -> dict[str, str]:
        """
        Reconstruct the full variable state at the current cursor by replaying
        all delta snapshots from step 0 up to (and including) cursor.

        Optionally filter to a specific filename and func_name scope.
        """
        # Build incrementally (check cache for closest lower key)
        state = self._build_state(self._cursor, filename, func_name)
        return state

    def _build_state(
        self,
        up_to: int,
        filename: str | None,
        func_name: str | None,
    ) -> dict[str, str]:
        """Replay all variable deltas from 0..up_to."""
        state: dict[str, str] = {}
        for i in range(up_to + 1):
            ev = self.store.get(i)
            if ev is None:
                break
            if filename and ev.frame.filename != filename:
                continue
            if func_name and ev.frame.func_name != func_name:
                continue
            if ev.vars and ev.vars.changed:
                for name, val in ev.vars.changed.items():
                    if val == "<deleted>":
                        state.pop(name, None)
                    else:
                        state[name] = val
        return state

    # ──────────────────────────────────────────────────────────────────────────
    # Search
    # ──────────────────────────────────────────────────────────────────────────

    def next_event_of_kind(self, kind: EventKind, from_step: int | None = None) -> int | None:
        """Return step_index of next event of given kind after from_step."""
        start = (from_step if from_step is not None else self._cursor) + 1
        for i in range(start, self.total):
            if self.store[i].kind == kind:
                return i
        return None

    def prev_event_of_kind(self, kind: EventKind, from_step: int | None = None) -> int | None:
        """Return step_index of previous event of given kind before from_step."""
        start = (from_step if from_step is not None else self._cursor) - 1
        for i in range(start, -1, -1):
            if self.store[i].kind == kind:
                return i
        return None

    def find_var_change(self, var_name: str, direction: str = "next") -> int | None:
        """
        Jump to next/prev event where `var_name` changed.
        direction: 'next' or 'prev'
        """
        history = self.store.var_history(var_name)
        steps = [r["step_index"] for r in history]
        if not steps:
            return None
        if direction == "next":
            for s in steps:
                if s > self._cursor:
                    return s
        else:
            for s in reversed(steps):
                if s < self._cursor:
                    return s
        return None

    def find_exception(self, direction: str = "next") -> int | None:
        """Jump to next/prev EXCEPTION event."""
        return (
            self.next_event_of_kind(EventKind.EXCEPTION)
            if direction == "next"
            else self.prev_event_of_kind(EventKind.EXCEPTION)
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Summary for current frame
    # ──────────────────────────────────────────────────────────────────────────

    def current_frame_summary(self) -> dict:
        ev = self.current_event()
        if ev is None:
            return {}
        state = self.current_state(
            filename=ev.frame.filename,
            func_name=ev.frame.func_name,
        )
        source_lines = self.store.get_source(ev.frame.filename)
        src_line = (
            source_lines[ev.lineno - 1] if source_lines and 1 <= ev.lineno <= len(source_lines)
            else None
        )
        return {
            "step_index":   ev.step_index,
            "kind":         ev.kind.name,
            "filename":     ev.frame.filename,
            "func_name":    ev.frame.func_name,
            "lineno":       ev.lineno,
            "depth":        ev.depth,
            "timestamp_ms": round(ev.timestamp * 1000, 3),
            "source_line":  src_line,
            "locals":       state,
            "return_value": ev.return_value,
            "exception":    ev.exception,
            "total":        self.total,
            "cursor":       self._cursor,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Call tree
    # ──────────────────────────────────────────────────────────────────────────

    def call_tree(self) -> list[dict]:
        """
        Build a flame-chart-compatible call tree from all CALL/RETURN events.
        Returns a list of spans: {func, filename, start_step, end_step, depth, children}.
        """
        stack: list[dict] = []
        roots: list[dict] = []

        for ev in self.store.iter_events():
            if ev.kind == EventKind.CALL:
                node = {
                    "func":       ev.frame.func_name,
                    "filename":   ev.frame.filename,
                    "start_step": ev.step_index,
                    "end_step":   ev.step_index,
                    "depth":      ev.depth,
                    "children":   [],
                }
                if stack:
                    stack[-1]["children"].append(node)
                else:
                    roots.append(node)
                stack.append(node)
            elif ev.kind == EventKind.RETURN and stack:
                node = stack.pop()
                node["end_step"] = ev.step_index
                node["return_value"] = ev.return_value

        return roots
