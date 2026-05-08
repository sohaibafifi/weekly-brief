"""Typer CLI entrypoint."""
from __future__ import annotations

import logging
import webbrowser
from pathlib import Path

import typer
from rich import print as rprint
from rich.logging import RichHandler

from weekly_brief.config import load_config
from weekly_brief.pipeline import run_pipeline

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Weekly brief CLI")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, show_time=False, show_path=False)],
    )


@app.command()
def run(
    config: Path = typer.Option(None, "--config", "-c"),
    week: str = typer.Option("next", "--week", help="'next' or 'current'"),
    no_email: bool = typer.Option(False, "--no-email"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Build brief and send email."""
    _setup_logging(verbose)
    cfg = load_config(config)
    out = run_pipeline(cfg, send=not no_email, week=week)
    rprint(f"[green]✓[/green] {out}")


@app.command()
def preview(
    config: Path = typer.Option(None, "--config", "-c"),
    week: str = typer.Option("next", "--week"),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Build brief without sending email; opens HTML in default browser."""
    _setup_logging(verbose)
    cfg = load_config(config)
    out = run_pipeline(cfg, send=False, week=week)
    if open_browser:
        webbrowser.open((out / "index.html").as_uri())
    rprint(f"[green]✓[/green] {out}")


if __name__ == "__main__":
    app()
