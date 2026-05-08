"""Typer CLI entrypoint."""
from __future__ import annotations

import logging
import webbrowser
from pathlib import Path

import typer
from rich import print as rprint
from rich.logging import RichHandler

from weekly_brief.config import load_config

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Weekly brief CLI")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, show_time=False, show_path=False)],
    )


def _cfg(config: Path | None):
    return load_config(config)


@app.command()
def run(
    config: Path = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    week: str = typer.Option("next", "--week", help="'next' or 'current'"),
    no_email: bool = typer.Option(False, "--no-email", help="Skip SMTP send"),
    debug_smtp: bool = typer.Option(False, "--debug-smtp", help="Print SMTP conversation"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Build brief and send email (default)."""
    _setup_logging(verbose or debug_smtp)
    from weekly_brief.pipeline import run_pipeline

    cfg = _cfg(config)
    try:
        out = run_pipeline(cfg, send=not no_email, week=week, debug_smtp=debug_smtp)
    except Exception as exc:
        rprint(f"[red]✗ pipeline failed:[/red] {type(exc).__name__}: {exc}")
        raise typer.Exit(code=1)
    rprint(f"[green]✓[/green] Outputs at {out}")
    rprint(f"[blue]file://{out}/index.html[/blue]")


@app.command()
def preview(
    config: Path = typer.Option(None, "--config", "-c"),
    week: str = typer.Option("next", "--week"),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Build brief without sending email; opens HTML in default browser."""
    _setup_logging(verbose)
    from weekly_brief.pipeline import run_pipeline

    cfg = _cfg(config)
    out = run_pipeline(cfg, send=False, week=week)
    html = out / "index.html"
    rprint(f"[green]✓[/green] Outputs at {out}")
    if open_browser:
        webbrowser.open(html.as_uri())


@app.command("test-ics")
def test_ics(config: Path = typer.Option(None, "--config", "-c")):
    """Fetch each ICS URL and print event count for the coming week."""
    cfg = _cfg(config)
    from weekly_brief.calendars import collect_events
    from weekly_brief.timeutil import next_week_bounds, now_in

    ws, we = next_week_bounds(now_in(cfg.timezone), cfg.timezone)
    events = collect_events(cfg, ws, we)
    by_src: dict[str, int] = {}
    for ev in events:
        by_src[ev.source_name] = by_src.get(ev.source_name, 0) + 1
    rprint(f"Window: {ws} → {we}")
    rprint(f"Total events: [bold]{len(events)}[/bold]")
    for k, v in by_src.items():
        rprint(f"  {k}: {v}")


@app.command("test-imap")
def test_imap(config: Path = typer.Option(None, "--config", "-c")):
    """Login + small fetch."""
    cfg = _cfg(config)
    from weekly_brief.mail import MailClient

    mc = MailClient(cfg)
    rprint("Login OK?", mc.ping())
    flagged = mc.fetch_flagged(30)
    rprint(f"Flagged last 30d: [bold]{len(flagged)}[/bold]")


@app.command("test-smtp")
def test_smtp(
    config: Path = typer.Option(None, "--config", "-c"),
    debug: bool = typer.Option(False, "--debug", help="Print full SMTP conversation"),
):
    """Send tiny test email to self."""
    _setup_logging(verbose=True)
    cfg = _cfg(config)
    from weekly_brief.notify import ping

    rprint(
        f"SMTP target: [cyan]{cfg.smtp.host}:{cfg.smtp.port}[/cyan] "
        f"as [cyan]{cfg.smtp.user}[/cyan] → [cyan]{cfg.smtp.to}[/cyan]"
    )
    try:
        ping(cfg, debug=debug)
    except Exception as exc:
        rprint(f"[red]✗ SMTP test FAILED:[/red] {type(exc).__name__}: {exc}")
        raise typer.Exit(code=1)
    rprint(f"[green]✓[/green] Test mail sent to {cfg.smtp.to}")


@app.command()
def diagnose(config: Path = typer.Option(None, "--config", "-c")):
    """Run ICS + IMAP + SMTP + LLM connectivity checks in one shot."""
    _setup_logging(verbose=True)
    cfg = _cfg(config)
    rprint("[bold]ICS[/bold]")
    try:
        from weekly_brief.calendars import collect_events
        from weekly_brief.timeutil import next_week_bounds, now_in

        ws, we = next_week_bounds(now_in(cfg.timezone), cfg.timezone)
        events = collect_events(cfg, ws, we)
        rprint(f"  [green]✓[/green] {len(events)} events for {ws.date()} → {we.date()}")
    except Exception as exc:
        rprint(f"  [red]✗[/red] {type(exc).__name__}: {exc}")

    rprint("[bold]IMAP[/bold]")
    try:
        from weekly_brief.mail import MailClient

        MailClient(cfg).ping()
        rprint("  [green]✓[/green] login OK")
    except Exception as exc:
        rprint(f"  [red]✗[/red] {type(exc).__name__}: {exc}")

    rprint("[bold]SMTP[/bold]")
    try:
        from weekly_brief.notify import ping

        ping(cfg)
        rprint(f"  [green]✓[/green] test mail sent to {cfg.smtp.to}")
    except Exception as exc:
        rprint(f"  [red]✗[/red] {type(exc).__name__}: {exc}")

    rprint("[bold]LLM[/bold]")
    try:
        from weekly_brief.llm import MistralClient

        out = MistralClient(cfg.llm).ping()
        rprint(f"  [green]✓[/green] {out!r}")
    except Exception as exc:
        rprint(f"  [red]✗[/red] {type(exc).__name__}: {exc}")

    rprint("[bold]Notion[/bold]")
    try:
        from weekly_brief.notion import NotionClient

        client = NotionClient(cfg.notion)
        if not client.enabled:
            rprint("  [yellow]disabled[/yellow]")
        else:
            out = client.ping()
            rprint(f"  [green]✓[/green] DB OK: {out!r}")
    except Exception as exc:
        rprint(f"  [red]✗[/red] {type(exc).__name__}: {exc}")


@app.command("test-llm")
def test_llm(config: Path = typer.Option(None, "--config", "-c")):
    """Send a 5-token ping to Mistral."""
    cfg = _cfg(config)
    from weekly_brief.llm import MistralClient

    out = MistralClient(cfg.llm).ping()
    rprint(f"[green]✓[/green] Mistral OK: {out!r}")


@app.command("test-notion")
def test_notion(config: Path = typer.Option(None, "--config", "-c")):
    """Verify Notion API key + database access."""
    _setup_logging(verbose=True)
    cfg = _cfg(config)
    from weekly_brief.notion import NotionClient

    client = NotionClient(cfg.notion)
    if not client.enabled:
        rprint(
            "[yellow]Notion disabled.[/yellow] Set notion.enabled=true, fill database_id, "
            f"export {cfg.notion.api_key_env}."
        )
        raise typer.Exit(code=1)
    try:
        out = client.ping()
    except Exception as exc:
        rprint(f"[red]✗ Notion test FAILED:[/red] {type(exc).__name__}: {exc}")
        raise typer.Exit(code=1)
    rprint(f"[green]✓[/green] Notion DB reachable: {out!r}")


if __name__ == "__main__":
    app()
