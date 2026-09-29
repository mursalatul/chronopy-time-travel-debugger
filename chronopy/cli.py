#!/usr/bin/env python3
"""
ChronoPy CLI — record, replay, and inspect Python program traces.

Usage:
    chronopy record script.py          # Record and save trace
    chronopy record script.py --serve  # Record and immediately open UI
    chronopy serve trace.chronopy      # Serve a saved trace in the UI
    chronopy inspect trace.chronopy    # CLI inspection (no browser)
"""

from __future__ import annotations

import os
import sys
import webbrowser
from pathlib import Path

import click
import uvicorn
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box

from chronopy.tracer.core import HybridTracer, run_file
from chronopy.tracer.store import TraceStore
from chronopy.replay.engine import ReplayEngine
from chronopy.server.app import create_app

console = Console()


# ─── record ──────────────────────────────────────────────────────────────────

@click.group()
@click.version_option("0.1.0", prog_name="chronopy")
def cli():
    """⏪ ChronoPy — A time-travel debugger for Python."""
    pass


@cli.command()
@click.argument("script", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", default=None, help="Output .chronopy file path")
@click.option("--serve/--no-serve", default=True, help="Open web UI after recording")
@click.option("--port", default=7331, help="Web UI port (default: 7331)")
@click.option("--max-events", default=500_000, help="Maximum events to record")
def record(script: str, output: str, serve: bool, port: int, max_events: int):
    """Record a Python script's execution and (optionally) open the web UI."""
    script_path = str(Path(script).resolve())
    if output is None:
        stem = Path(script).stem
        output = str(Path(script).parent / f"{stem}.chronopy")

    console.print(Panel.fit(
        f"[bold cyan]ChronoPy[/] — recording [green]{script_path}[/]",
        border_style="cyan",
    ))

    tracer = HybridTracer(target_file=script_path, max_events=max_events)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Running and tracing…", total=None)
        tracer = run_file(script_path, tracer=tracer)

    store = tracer.store
    summary = store.summary()

    # Print summary table
    table = Table(title="Trace Summary", box=box.ROUNDED, border_style="cyan")
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="bold white")
    table.add_row("Total events",   str(summary.get("total_events", 0)))
    table.add_row("Duration",       f"{summary.get('duration_ms', 0):.3f} ms")
    table.add_row("Max call depth", str(summary.get("max_depth", 0)))
    table.add_row("Functions",      str(len(summary.get("functions", []))))
    for kind, count in summary.get("kind_counts", {}).items():
        table.add_row(f"  {kind}", str(count))
    console.print(table)

    # Save
    store.save(output)
    console.print(f"[green]✓[/] Trace saved → [cyan]{output}[/]")

    if serve:
        _launch_server(store, port)


@cli.command()
@click.argument("trace_file", type=click.Path(exists=True))
@click.option("--port", default=7331, help="Web UI port (default: 7331)")
def serve(trace_file: str, port: int):
    """Serve a saved .chronopy trace in the web UI."""
    console.print(f"[cyan]Loading trace:[/] {trace_file}")
    store = TraceStore.load(trace_file)
    summary = store.summary()
    console.print(f"[green]✓[/] Loaded {summary.get('total_events', 0):,} events")
    _launch_server(store, port)


@cli.command()
@click.argument("trace_file", type=click.Path(exists=True))
def inspect(trace_file: str):
    """CLI-based interactive inspection of a .chronopy trace."""
    console.print(f"[cyan]Loading trace:[/] {trace_file}")
    store = TraceStore.load(trace_file)
    engine = ReplayEngine(store)

    console.print(Panel.fit(
        "[bold]ChronoPy CLI Inspector[/]\n"
        "[dim]Commands: n=next, p=prev, N10=+10, P10=-10, j<n>=jump, v<name>=var-history, q=quit[/]",
        border_style="cyan",
    ))

    while True:
        summary = engine.current_frame_summary()
        _print_frame(summary)

        try:
            cmd = console.input("[dim]chronopy>[/] ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if cmd == "q":
            break
        elif cmd == "n":
            engine.step_forward()
        elif cmd == "p":
            engine.step_backward()
        elif cmd.startswith("N"):
            n = int(cmd[1:] or "10")
            engine.step_forward(n)
        elif cmd.startswith("P"):
            n = int(cmd[1:] or "10")
            engine.step_backward(n)
        elif cmd.startswith("j"):
            step = int(cmd[1:])
            engine.jump_to(step)
        elif cmd.startswith("v"):
            var = cmd[1:].strip()
            history = store.var_history(var)
            if not history:
                console.print(f"[red]No history for '{var}'[/]")
            else:
                t = Table(title=f"History of '{var}'", box=box.SIMPLE)
                t.add_column("Step"); t.add_column("Value"); t.add_column("Location")
                for h in history[:50]:
                    t.add_row(
                        str(h["step_index"]),
                        h["value"][:60],
                        f"{Path(h['filename']).name}:{h['lineno']}",
                    )
                console.print(t)
        elif cmd.startswith("e"):
            step = engine.find_exception("next")
            if step is not None:
                engine.jump_to(step)
                console.print(f"[red]Jumped to exception at step {step}[/]")
            else:
                console.print("[dim]No more exceptions[/]")
        else:
            console.print("[dim]Unknown command. n/p/N<n>/P<n>/j<n>/v<name>/e/q[/]")

    console.print("[cyan]Goodbye![/]")


def _print_frame(s: dict):
    kind_colors = {
        "CALL": "purple", "RETURN": "green",
        "LINE": "blue", "EXCEPTION": "red", "VAR_CHANGE": "yellow",
    }
    kind = s.get("kind", "?")
    color = kind_colors.get(kind, "white")

    t = Table(box=box.SIMPLE_HEAD, show_header=False, padding=(0, 1))
    t.add_column(style="dim")
    t.add_column(style="white")
    t.add_row("Step",     f"[bold]{s.get('cursor', '?')}[/] / {s.get('total', '?')}")
    t.add_row("Kind",     f"[{color}]{kind}[/]")
    t.add_row("Function", s.get("func_name", "?"))
    t.add_row("File",     Path(s.get("filename", "?")).name)
    t.add_row("Line",     str(s.get("lineno", "?")))
    if s.get("source_line"):
        t.add_row("Source",   f"[cyan]{s['source_line'].strip()}[/]")
    if s.get("exception"):
        t.add_row("Exception", f"[red]{s['exception']}[/]")
    if s.get("return_value") and kind == "RETURN":
        t.add_row("Return",   f"[green]{s['return_value']}[/]")
    console.print(t)

    # Variables
    locs = s.get("locals", {})
    if locs:
        vt = Table(box=box.SIMPLE, title="Locals", show_header=True, title_style="dim")
        vt.add_column("Name",  style="blue")
        vt.add_column("Value", style="green")
        for name, val in list(locs.items())[:20]:
            vt.add_row(name, str(val)[:80])
        console.print(vt)


def _launch_server(store: TraceStore, port: int):
    app = create_app(store)
    url = f"http://localhost:{port}"
    console.print(f"\n[bold cyan]⏪ ChronoPy UI →[/] [underline]{url}[/]\n")
    webbrowser.open(url)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    cli()
