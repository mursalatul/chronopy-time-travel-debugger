"""
TraceStore — the in-memory log of all recorded events.

Design goals:
  • Append-only, O(1) append
  • Efficient random access by step_index
  • Compact serialisation to/from disk via msgpack
  • Variable history queries: "when did var X change?"
  • Causal slicing index: per-variable provenance chain
"""

from __future__ import annotations

import gzip
import io
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterator, Optional

import msgpack

from .events import Event, EventKind, FrameInfo, VarSnapshot


class TraceStore:
    """
    Stores all execution events and provides query interfaces.
    """

    def __init__(self):
        self._events: list[Event] = []
        # var_history[filename][func_name][var_name] -> list of step_indices
        self._var_history: dict[str, dict[str, dict[str, list[int]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )
        # Source cache: filename -> list of source lines
        self._source_cache: dict[str, list[str]] = {}

    # ──────────────────────────────────────────────────────────────────────────
    # Append
    # ──────────────────────────────────────────────────────────────────────────

    def append(self, event: Event):
        self._events.append(event)

    def attach_vars_to_last(
        self,
        filename: str,
        lineno: int,
        vars: VarSnapshot,
    ):
        """
        Find the most recent event matching filename/lineno and attach vars to it.
        Works backwards from the end for O(1) amortised access.
        """
        for i in range(len(self._events) - 1, max(len(self._events) - 20, -1), -1):
            ev = self._events[i]
            if ev.frame.filename == filename and ev.lineno == lineno:
                ev.vars = vars
                # Index variable changes
                if vars.changed:
                    for name in vars.changed:
                        self._var_history[filename][ev.frame.func_name][name].append(
                            ev.step_index
                        )
                return

    # ──────────────────────────────────────────────────────────────────────────
    # Access
    # ──────────────────────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._events)

    def __getitem__(self, idx: int) -> Event:
        return self._events[idx]

    def get(self, step_index: int) -> Optional[Event]:
        if 0 <= step_index < len(self._events):
            return self._events[step_index]
        return None

    def events(self) -> list[Event]:
        return self._events

    def iter_events(self, start: int = 0, end: int | None = None) -> Iterator[Event]:
        end = end or len(self._events)
        yield from self._events[start:end]

    # ──────────────────────────────────────────────────────────────────────────
    # Summary / metadata
    # ──────────────────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        """Return high-level statistics about this trace."""
        if not self._events:
            return {"total_events": 0}

        first = self._events[0]
        last  = self._events[-1]
        duration = last.timestamp - first.timestamp

        kind_counts: dict[str, int] = defaultdict(int)
        files: set[str] = set()
        funcs: set[str] = set()
        for ev in self._events:
            kind_counts[ev.kind.name] += 1
            files.add(ev.frame.filename)
            funcs.add(ev.frame.func_name)

        return {
            "total_events": len(self._events),
            "duration_ms":  round(duration * 1000, 3),
            "kind_counts":  dict(kind_counts),
            "files":        sorted(files),
            "functions":    sorted(funcs),
            "max_depth":    max(ev.depth for ev in self._events),
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Variable history
    # ──────────────────────────────────────────────────────────────────────────

    def var_history(self, var_name: str) -> list[dict]:
        """
        Return all events where `var_name` changed, across all frames.
        Useful for the "when did X change?" query.
        """
        results = []
        for filename, funcs in self._var_history.items():
            for func_name, vars in funcs.items():
                if var_name in vars:
                    for step_idx in vars[var_name]:
                        ev = self.get(step_idx)
                        if ev and ev.vars:
                            results.append({
                                "step_index": step_idx,
                                "filename":   filename,
                                "func_name":  func_name,
                                "lineno":     ev.lineno,
                                "value":      ev.vars.changed.get(var_name, "?"),
                                "timestamp":  ev.timestamp,
                            })
        results.sort(key=lambda r: r["step_index"])
        return results

    def all_var_names(self) -> list[str]:
        """Return sorted unique variable names across the whole trace."""
        names: set[str] = set()
        for funcs in self._var_history.values():
            for vars in funcs.values():
                names.update(vars.keys())
        return sorted(names)

    # ──────────────────────────────────────────────────────────────────────────
    # Causal slicing
    # ──────────────────────────────────────────────────────────────────────────

    def causal_chain(self, step_index: int, var_name: str) -> list[dict]:
        """
        Return the causal chain of events that produced `var_name`'s value
        at `step_index`.

        Algorithm (simplified backward data-flow):
        1. Find the last write to `var_name` at or before `step_index`.
        2. For each assignment line, collect the other variables it read
           (by scanning the source line for names).
        3. Recursively trace back those variables.

        Returns a list of event dicts ordered from earliest to latest.
        """
        target_ev = self.get(step_index)
        if target_ev is None:
            return []

        chain_steps: set[int] = set()
        self._trace_var_backwards(
            var_name=var_name,
            up_to_step=step_index,
            filename=target_ev.frame.filename,
            func_name=target_ev.frame.func_name,
            visited=chain_steps,
            depth=0,
            max_depth=8,
        )

        result = []
        for si in sorted(chain_steps):
            ev = self.get(si)
            if ev:
                result.append(ev.to_dict())
        return result

    def _trace_var_backwards(
        self,
        var_name: str,
        up_to_step: int,
        filename: str,
        func_name: str,
        visited: set[int],
        depth: int,
        max_depth: int,
    ):
        if depth >= max_depth:
            return

        history = self._var_history.get(filename, {}).get(func_name, {}).get(var_name, [])
        # Find the last write before up_to_step
        write_step = None
        for si in reversed(history):
            if si <= up_to_step:
                write_step = si
                break

        if write_step is None or write_step in visited:
            return

        visited.add(write_step)
        ev = self.get(write_step)
        if ev is None:
            return

        # Find names used on that source line and recurse
        source_line = self._get_source_line(filename, ev.lineno)
        if source_line:
            import ast
            try:
                tree = ast.parse(source_line.strip(), mode="exec")
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                        if node.id != var_name and not node.id.startswith("__"):
                            self._trace_var_backwards(
                                var_name=node.id,
                                up_to_step=write_step,
                                filename=filename,
                                func_name=func_name,
                                visited=visited,
                                depth=depth + 1,
                                max_depth=max_depth,
                            )
            except SyntaxError:
                pass

    def _get_source_line(self, filename: str, lineno: int) -> str | None:
        if filename not in self._source_cache:
            try:
                lines = Path(filename).read_text(errors="replace").splitlines()
                self._source_cache[filename] = lines
            except Exception:
                self._source_cache[filename] = []
        lines = self._source_cache.get(filename, [])
        if 1 <= lineno <= len(lines):
            return lines[lineno - 1]
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Source code access
    # ──────────────────────────────────────────────────────────────────────────

    def get_source(self, filename: str) -> list[str]:
        """Return source lines for a given filename (0-indexed)."""
        if filename not in self._source_cache:
            try:
                lines = Path(filename).read_text(errors="replace").splitlines()
                self._source_cache[filename] = lines
            except Exception:
                self._source_cache[filename] = []
        return self._source_cache[filename]

    # ──────────────────────────────────────────────────────────────────────────
    # Serialisation
    # ──────────────────────────────────────────────────────────────────────────

    def save(self, path: str | Path):
        """Save the trace to a gzip-compressed msgpack file (.chronopy)."""
        path = Path(path)
        records = [ev.to_dict() for ev in self._events]
        payload = {
            "version":  1,
            "summary":  self.summary(),
            "events":   records,
            "sources":  {k: v for k, v in self._source_cache.items()},
        }
        raw = msgpack.packb(payload, use_bin_type=True)
        with gzip.open(path, "wb") as f:
            f.write(raw)

    @classmethod
    def load(cls, path: str | Path) -> "TraceStore":
        """Load a trace from a .chronopy file."""
        path = Path(path)
        with gzip.open(path, "rb") as f:
            raw = f.read()
        payload = msgpack.unpackb(raw, raw=False)

        store = cls()
        store._source_cache = payload.get("sources", {})

        for rec in payload["events"]:
            frame = FrameInfo(
                func_name=rec["frame"]["func_name"],
                filename=rec["frame"]["filename"],
                lineno=rec["frame"]["lineno"],
                frame_id=rec["frame"]["frame_id"],
            )
            kind = EventKind[rec["kind"]]
            vars_snap = None
            if "vars_changed" in rec:
                vars_snap = VarSnapshot(
                    changed=rec["vars_changed"],
                    full_locals=rec.get("vars_full"),
                )
            ev = Event(
                step_index=rec["step_index"],
                kind=kind,
                timestamp=rec["timestamp"],
                frame=frame,
                lineno=rec["lineno"],
                return_value=rec.get("return_value"),
                exception=rec.get("exception"),
                vars=vars_snap,
                parent_step=rec.get("parent_step"),
                depth=rec.get("depth", 0),
            )
            store._events.append(ev)

            # Rebuild var_history index
            if vars_snap and vars_snap.changed:
                for name in vars_snap.changed:
                    store._var_history[frame.filename][frame.func_name][name].append(
                        ev.step_index
                    )

        return store
