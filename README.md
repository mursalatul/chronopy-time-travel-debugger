# ⏪ ChronoPy — Time-Travel Debugger for Python

> **Run your Python program. Then go back in time.**
> ChronoPy records every line, every function call, and every variable change in your program's execution — and lets you scrub through it like a video, jump to any moment, and ask "why did this variable end up here?"

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-teal)](https://fastapi.tiangolo.com)

---

## Table of Contents

- [What Is ChronoPy?](#what-is-chronopy)
- [When Is It Useful?](#when-is-it-useful)
- [Quick Start](#quick-start)
- [Understanding the Web UI](#understanding-the-web-ui)
- [Step-by-Step Usage Guide](#step-by-step-usage-guide)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [CLI Reference](#cli-reference)
- [How It Works (Architecture)](#how-it-works)
- [Roadmap](#roadmap)

---

## What Is ChronoPy?

Traditional debuggers are **forward-only**. You set a breakpoint, you run, and if you miss the moment the bug happened — you start over. ChronoPy is different.

ChronoPy **records** your Python program's entire execution into a compact trace file, then lets you:

- **Rewind and replay** — step backward and forward through every line that ran
- **Scrub like a video** — drag a timeline slider to any point in execution
- **Inspect variables** — see the exact value of every local variable at every moment
- **Trace causality** — click a variable and ask *"what chain of statements caused this value?"*
- **Jump to exceptions** — teleport instantly to where an error was raised
- **See variable history** — view every time a variable changed across the whole program

It works on **any Python script** — no code changes needed. Just prefix your command with `chronopy record`.

```
Normal run:     python my_script.py
With ChronoPy:  chronopy record my_script.py
```

---

## When Is It Useful?

### 🐛 Debugging a Hard-to-Reproduce Bug
Your program produces a wrong result, but you're not sure where things went wrong. With a traditional debugger you'd add print statements and re-run. With ChronoPy, you run once, then explore the full history freely — no re-runs needed.

### 🔍 Understanding Unfamiliar Code
You inherited a codebase and don't know what it does. Run it under ChronoPy, then watch the execution: which functions are called, in what order, with what data. The flame chart gives you a visual call-tree instantly.

### 📚 Learning How Something Works
Want to understand how Python's standard library handles a particular case? Trace it. Watch every function call and return, inspect the internal variables, see how data flows.

### 🧪 Verifying Algorithm Correctness
Implementing a sorting algorithm? Run it under ChronoPy and watch every swap happen, step by step, with full variable state at each iteration.

### 💥 Post-Mortem Analysis
Your script crashed. ChronoPy captured the full execution including the exception and all variables at that moment. Jump straight to the exception and look backward to see exactly what led to it.

---

## Quick Start

### Prerequisites

- Python **3.12 or newer** (required for `sys.monitoring` — the low-overhead tracing API)
- The project virtual environment

### 1. Activate the environment

```bash
conda activate ./chronopy_venv
# or, if using the venv directly:
source chronopy_venv/bin/activate
```

### 2. Record a script and open the UI

```bash
chronopy record examples/example_buggy.py
```

This will:
1. Run `example_buggy.py` with full tracing enabled
2. Print a summary table in your terminal
3. Save a trace file (`example_buggy.chronopy`)
4. Open your browser at **http://localhost:7331**

### 3. Explore the trace

Use the timeline, click events, inspect variables — everything is in the browser.

### 4. Serve a saved trace later (without re-running)

```bash
chronopy serve examples/example_buggy.chronopy
```

### 5. Use the CLI inspector (terminal-only, no browser)

```bash
chronopy inspect examples/example_buggy.chronopy
```

---

## Understanding the Web UI

The UI has **five main areas**. Here's a complete guide to each one.

```
┌─────────────────────────────── Header ──────────────────────────────────┐
├────────────────────── Execution Timeline (scrubber) ────────────────────┤
│ Left Panel     │       Centre Panel        │      Right Panel           │
│ (Event List)   │    (Source Code View)     │   (State Inspector)        │
│                │                           │                            │
│                ├──────── Flame Chart ───────┤                            │
└────────────────┴───────────────────────────┴────────────────────────────┘
└───────────────────────────── Status Bar ────────────────────────────────┘
```

---

### 🔷 Header

| Element | What it does |
|---------|-------------|
| **⏪ ChronoPy** | The logo — click to return to step 0 |
| **Step X of Y** | Your current position in the execution. X = current step, Y = total recorded steps |
| **⚡ Jump to Exception** | Teleports the cursor to the next recorded exception (error) in the trace |
| **🔗 Causal Chain** | Opens the Causal Chain analysis for whichever variable you've selected in the State Inspector |
| **Connected / Reconnecting** | Whether the browser is connected to the live backend via WebSocket. If disconnected, changes won't sync — it will reconnect automatically |

---

### 🔷 Execution Timeline (Scrubber)

This is the main time-travel control. Think of it like a video player scrubber.

```
«   ‹   ▶   ›   »   [═══════■══════════════════════]
```

| Control | Action |
|---------|--------|
| **«** | Jump backward 10 steps |
| **‹** | Go back 1 step |
| **▶ / ⏸** | Play through the execution automatically (100ms per step). Click again to pause |
| **›** | Advance 1 step |
| **»** | Jump forward 10 steps |
| **Minimap bar** | A visual overview of the entire execution. Purple spikes = function calls, green spikes = returns, red spikes = exceptions. Click anywhere to jump there |
| **Slider** | Drag to any point in the execution. The filled blue portion shows how far you are |
| **Timestamp** | Shows the elapsed time (in milliseconds) at the current step |

---

### 🔷 Left Panel — Event List

Every recorded execution event is listed here in order. Each row is one "step" in the trace.

**Event types and what they mean:**

| Badge | Colour | Meaning |
|-------|--------|---------|
| `CALL` | Light purple | A function was called. The program entered a new function |
| `RETURN` | Light green | A function returned a value and exited |
| `LINE` | Light blue | A source line was executed |
| `EXCEPTION` | Light red | An exception was raised at this point |

**Reading an event row:**

```
[ CALL ]  fibonacci              examples/example_buggy.py    :14
 ↑badge   ↑function name         ↑file                        ↑line number
```

- The **indentation** of the function name reflects the call depth — deeper indented = deeper in the call stack
- For `RETURN` events, the return value is shown in the meta line
- For `EXCEPTION` events, the exception message is shown

**Filtering events:**
- Click **All / Call / Return / Line / Exception** chips to show only that type
- Type in the **search box** to filter by function name or file name

**Clicking an event** jumps the entire UI to that exact step — the source view, variable inspector, and scrubber all update instantly.

---

### 🔷 Centre Panel — Source Code View

Shows the actual Python source code for the file being executed, highlighted at the **current line**.

| Visual indicator | Meaning |
|-----------------|---------|
| **Blue left border + highlighted row** | The line currently being executed at your cursor position |
| **Line numbers** | Numbered from the start of the file — click an event to jump to its line |
| **Colour-coded syntax** | Keywords (purple), strings (green), numbers (amber), functions (blue), class names (brown) |

The view automatically scrolls to keep the current line visible as you step through.

---

### 🔷 Flame Chart (bottom of centre panel)

A horizontal call-stack visualisation of the **entire** execution.

```
[═══════════════════ <module> ══════════════════════════]
  [═══ fibonacci ══][═ collatz ═][═══ buggy_sort ═══]
     [fib][fib][fib]               [sort inner loop]
```

- Each **coloured bar** = one function call, spanning from when it was called to when it returned
- **Nested bars** = functions called inside other functions (deeper = more indented)
- The **vertical blue line** shows where you currently are in time
- **Click anywhere** on the flame chart to jump to that point in the execution

Wider bars = functions that ran for longer (more steps). Narrow slivers = short/fast functions.

---

### 🔷 Right Panel — State Inspector

This panel shows **what the program's state looks like right now** (at your current step).

#### Frame Info card

| Field | Meaning |
|-------|---------|
| **Function** | The name of the function currently executing |
| **File** | The source file being executed |
| **Line** | The line number currently active |
| **Call Depth** | How many functions deep you are (0 = top level, 1 = called from top, etc.) |
| **Elapsed** | Time since the program started, in milliseconds |

#### Current Line card

Shows the exact line of source code being executed — useful when you're switching between different files.

#### Local Variables

Every local variable in the current function scope, with its current value.

| Control | Action |
|---------|--------|
| **Click a variable row** | Selects (highlights) that variable — required before using Causal Chain |
| **⏱ button** | Opens the **Variable History** modal for that variable |

**Tip:** Variables are shown with their `repr()` — so a list shows `[1, 2, 3]`, a dict shows `{'key': 'val'}`, etc.

---

### 🔷 Variable History Modal (⏱)

Click the **⏱** button next to any variable to see every time it changed across the entire trace.

```
Variable History — arr

Step 45 · 1.234 ms
arr = [5, 3, 8, 1, 9, 2, 7, 4, 6]
buggy_sort · example_buggy.py · line 33

Step 47 · 1.267 ms
arr = [3, 5, 8, 1, 9, 2, 7, 4, 6]
buggy_sort · example_buggy.py · line 35
...
```

- Each entry shows the **step**, **timestamp**, **new value**, and **location** of the change
- **Click any entry** to jump the UI directly to that exact moment

---

### 🔷 Causal Chain Modal (🔗)

This is ChronoPy's most powerful feature. It answers: **"Why does this variable have this value?"**

**How to use it:**
1. Navigate to a step where a variable has a value you're curious about
2. **Click the variable row** in the State Inspector to select it (it highlights in blue)
3. Click **🔗 Causal Chain** in the header
4. The modal shows the chain of statements that produced the current value

**What it shows:**

```
Causal Chain — arr @ step 120

① LINE  · buggy_sort · line 33
   {"arr": "[5, 3, 8, 1, 9, 2, 7, 4, 6]"}

② LINE  · buggy_sort · line 35
   {"arr": "[3, 5, 8, 1, 9, 2, 7, 4, 6]"}

③ LINE  · buggy_sort · line 35
   {"arr": "[3, 5, 1, 8, 9, 2, 7, 4, 6]"}
```

Each node is a statement that contributed to the variable's value. **Click any node** to jump there.

---

## Step-by-Step Usage Guide

### Scenario: You have a bug and don't know where it is

**Step 1 — Record the buggy run**
```bash
chronopy record my_script.py
```
The browser opens automatically.

**Step 2 — Find the wrong output**
Look at your program's output in the terminal. Identify what value is wrong.

**Step 3 — Search for the relevant function**
In the **Event List** (left panel), type the function name in the search box.

**Step 4 — Jump to that function call**
Click the `CALL` event for that function. The source view and variable inspector update.

**Step 5 — Step through the function**
Use `→` (or the `›` button) to step forward one line at a time. Watch the variables in the right panel change.

**Step 6 — Spot where the value goes wrong**
When you see a variable change to an unexpected value, stop.

**Step 7 — Use Variable History**
Click the **⏱** button on that variable. See every previous value — find where it first went wrong.

**Step 8 — Use Causal Chain**
Click the variable to select it, then click **🔗 Causal Chain**. This traces the exact statements that produced the bad value.

---

### Scenario: You want to understand what a function does

1. Filter the Event List to **Call** events only
2. Search for the function name
3. Click the `CALL` event to jump to function entry
4. Check the **State Inspector** to see what arguments were passed in
5. Press `→` to step through the function body
6. When you hit the `RETURN` event, the return value is shown

---

### Scenario: An exception crashed your program

1. Click **⚡ Jump to Exception** in the header
2. The UI jumps to the exact step where the exception was raised
3. The **State Inspector** shows the exception message and all variables at that moment
4. Step backward with `←` to see what led to the crash

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `→` or `l` | Step forward 1 |
| `←` or `h` | Step backward 1 |
| `↓` | Step forward 10 |
| `↑` | Step backward 10 |
| `Space` | Toggle play / pause |
| `Esc` | Close any open modal |

---

## CLI Reference

### `chronopy record <script.py>`

Records a script and (by default) opens the web UI.

```bash
chronopy record my_script.py
chronopy record my_script.py --no-serve          # don't open browser
chronopy record my_script.py -o my_trace.chronopy  # custom output path
chronopy record my_script.py --port 8080           # use a different port
chronopy record my_script.py --max-events 100000   # limit event count
```

### `chronopy serve <trace.chronopy>`

Serves a previously saved trace in the web UI.

```bash
chronopy serve my_trace.chronopy
chronopy serve my_trace.chronopy --port 8080
```

### `chronopy inspect <trace.chronopy>`

Terminal-only interactive inspector. No browser required.

```bash
chronopy inspect my_trace.chronopy
```

**Inspector commands:**

| Command | Action |
|---------|--------|
| `n` | Next step |
| `p` | Previous step |
| `N10` | Forward 10 steps |
| `P10` | Backward 10 steps |
| `j150` | Jump to step 150 |
| `v result` | Show history of variable `result` |
| `e` | Jump to next exception |
| `q` | Quit |

---

## How It Works

ChronoPy uses a **two-layer tracing approach** designed for both completeness and low overhead:

### Layer 1 — `sys.monitoring` (Python 3.12+, PEP 669)
The primary hook. Fires for every function call (`PY_START`), return (`PY_RETURN`), exception (`RAISE`), and line execution (`LINE`). This API is significantly faster than the older `sys.settrace` for the call/return path.

### Layer 2 — `sys.settrace` companion
Runs alongside `sys.monitoring`, but **only for your target file**. This is what captures local variable values — something `sys.monitoring` doesn't provide access to. The overhead is limited because it only activates for the file being debugged.

### Delta encoding
Rather than storing the full variable state at every step (which would be enormous), ChronoPy stores **only what changed** since the last step. A `FrameSnapshotter` tracks the previous value of each variable and computes a diff.

### Causal slicing (backward data-flow)
The causal chain analysis works by:
1. Finding the last write to variable `X` before the target step
2. Parsing that source line with Python's `ast` module to find what other variables were *read*
3. Recursively tracing those variables backwards (up to 8 hops)

This is a simplified form of **dynamic program slicing** — a research topic in software engineering.

### Storage
Traces are saved as **gzip-compressed msgpack** (`.chronopy` files), which is very compact. A 2,600-event trace is typically under 50 KB on disk.

---

## Project Structure

```
chronopy/
├── tracer/
│   ├── core.py        # HybridTracer: sys.monitoring + sys.settrace
│   ├── events.py      # Event, EventKind, FrameInfo, VarSnapshot models
│   ├── snapshot.py    # Delta-encoded variable snapshots
│   └── store.py       # TraceStore: log, var index, causal slicer, serialisation
├── replay/
│   └── engine.py      # ReplayEngine: cursor, state reconstruction, search
├── server/
│   └── app.py         # FastAPI: REST endpoints + WebSocket
├── ui/
│   └── index.html     # Web UI: HTML + CSS + JavaScript (single file)
└── cli.py             # CLI entry point (Click + Rich)
examples/
└── example_buggy.py   # Demo script with a deliberate sorting bug
pyproject.toml         # Package config + CLI entry point
```

---

## Roadmap

| Milestone | Status | Description |
|-----------|--------|-------------|
| M1 — Tracer | ✅ Done | `sys.monitoring` + `sys.settrace` hybrid recording |
| M2 — CLI replay | ✅ Done | Step-backward/forward in the terminal |
| M3 — Variable history | ✅ Done | "When did X change?" query |
| M4 — Web UI | ✅ Done | Timeline, source view, flame chart, inspector |
| M5 — Causal slicing | ✅ Done | "Why is this value here?" backward analysis |
| M6 — Deterministic replay | 🔜 Planned | Capture and replay `random`, `time`, file I/O |
| M7 — Async/threads | 🔜 Planned | Full `asyncio` and threading support |
| M8 — Expression granularity | 🔜 Planned | AST instrumentation for sub-line tracing |

---

## License

MIT — see [LICENSE](LICENSE).
