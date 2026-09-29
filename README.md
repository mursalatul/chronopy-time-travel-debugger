# ⏪ ChronoPy — Time-Travel Debugger for Python

> Record any Python program's execution, then rewind, scrub, and query it in a stunning web UI — like a DVR for your code.

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-cyan?logo=python)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple)](LICENSE)

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔬 **Low-overhead tracing** | Uses Python 3.12's `sys.monitoring` (PEP 669) + `sys.settrace` hybrid for minimal slowdown |
| 📦 **Delta-encoded snapshots** | Only changed variables are stored per step — not the full heap |
| ⏪ **Time-travel replay** | Step forward/backward through any execution, jump to any step instantly |
| 🌐 **Visual web UI** | Dark-mode timeline scrubber, source viewer, variable inspector, flame chart |
| 🔗 **Causal slicing** | Click any variable → trace the exact chain of statements that produced its value |
| 📈 **Variable history** | "When did `x` change?" — see every write with value + context |
| 💥 **Exception navigation** | Jump to next/previous exception instantly |
| 🔥 **Flame chart** | Call-stack depth visualised over the entire execution timeline |
| 💾 **Compact serialisation** | Traces saved as gzip-compressed msgpack (`.chronopy` files) |
| 🖥 **CLI inspector** | Keyboard-driven REPL for quick trace inspection without a browser |

---

## 🚀 Quick Start

### 1. Activate the virtual environment

```bash
conda activate ./chronopy_venv
```

### 2. Record and open the UI in one command

```bash
chronopy record examples/example_buggy.py
```

This will:
- Trace the script's execution
- Print a summary to the terminal
- Save `examples/example_buggy.chronopy`
- Open the web UI at **http://localhost:7331**

### 3. Serve a saved trace later

```bash
chronopy serve examples/example_buggy.chronopy
```

### 4. CLI inspector (no browser)

```bash
chronopy inspect examples/example_buggy.chronopy
```

---

## 🎮 Web UI Guide

| Action | How |
|---|---|
| **Scrub** timeline | Drag the scrubber or click the minimap |
| **Step forward/back** | `→`/`←` keys, or `›`/`‹` buttons (hold for 10 steps) |
| **Play** | `Space` or ▶ button |
| **Jump to exception** | ⚡ Exception button |
| **Variable history** | Click the ⏱ button next to any variable |
| **Causal chain** | Click a variable to select it (highlighted), then 🔗 Causal Chain |
| **Filter events** | Click CALL / RETURN / LINE / EXC chips in the left panel |
| **Search** | Type in the filter box to search by function or file name |

---

## 📐 Architecture

```
chronopy/
├── tracer/
│   ├── core.py      # Tracer + HybridTracer (sys.monitoring + sys.settrace)
│   ├── events.py    # Event, EventKind, FrameInfo, VarSnapshot data models
│   ├── snapshot.py  # Delta-encoded variable snapshots with safe repr
│   └── store.py     # TraceStore — append-only log, var history index, causal slicer
├── replay/
│   └── engine.py    # ReplayEngine — cursor, state reconstruction, search
├── server/
│   └── app.py       # FastAPI backend: REST + WebSocket
├── ui/
│   └── index.html   # Web UI (single-file: HTML + CSS + JS)
└── cli.py           # Click CLI: record / serve / inspect
examples/
└── example_buggy.py # Demo with a deliberate sorting bug + exception
```

### How the tracer works

1. **`sys.monitoring`** (PEP 669, Python 3.12+) provides low-overhead hooks for `PY_START`, `PY_RETURN`, `LINE`, `RAISE` events. It's significantly faster than `sys.settrace` for the call/return path.

2. **`sys.settrace`** companion runs alongside, limited to the target file only, to capture local variable state at each line event.

3. **Delta encoding**: `FrameSnapshotter` tracks the previous value of each variable and only stores changes — keeping the trace compact.

4. **Causal slicing**: When you query the causal chain for variable `x` at step `N`, the store:
   - Finds the last write to `x` before step `N`
   - Parses the source line with `ast` to find what other variables were read
   - Recursively traces those variables backwards (up to 8 hops)

---

## 🛣 Roadmap (Milestones)

- [x] **M1** — Tracer records execution to compact log (`sys.monitoring` + `settrace`)
- [x] **M2** — Step-backward/forward replay in CLI
- [x] **M3** — Variable history and "when did this change?"
- [x] **M4** — Web UI with timeline scrubbing, source view, flame chart
- [x] **M5** — Causal slicing ("why is this value here?")
- [ ] **M6** — Deterministic replay of `random`, `time`, file I/O
- [ ] **M7** — Threads and `asyncio` support
- [ ] **M8** — AST-level instrumentation for expression-level granularity

---

## 🧪 Running the Example

The included `example_buggy.py` has a deliberate bug in `buggy_sort`:

```python
for j in range(n - i - 2):   # BUG: should be n - i - 1
```

**Demo flow:**
1. `chronopy record examples/example_buggy.py`
2. Open UI → search for `buggy_sort` in the event list
3. Navigate to the loop iterations
4. Click `arr` → ⏱ to see how it changes over time
5. Click `arr` → 🔗 Causal Chain to trace why the last element is wrong

---

## 📄 License

MIT
