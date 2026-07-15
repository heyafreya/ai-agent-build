"""CLI entry point for the K8s health monitor agent.

Usage:
    python -m 01-k8s-health-monitor.src.cli
    python -m 01-k8s-health-monitor.src.cli --namespace default
    python -m 01-k8s-health-monitor.src.cli --describe
    python -m 01-k8s-health-monitor.src.cli --watch
"""

import time
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown

from .agent import analyze

app = typer.Typer(
    name="k8s-health",
    help="Monitor your Kubernetes cluster and get plain-English pod health summaries.",
)
console = Console()


@app.command()
def health(
    namespace: Optional[str] = typer.Option(
        None, "--namespace", "-n", help="Filter to a specific namespace."
    ),
    describe: bool = typer.Option(
        False,
        "--describe",
        "-d",
        help="Fetch detailed descriptions for unhealthy pods.",
    ),
    watch: bool = typer.Option(
        False,
        "--watch",
        "-w",
        help="Continuously monitor and re-analyze every 30 seconds.",
    ),
):
    """Analyze pod health and return a plain-English summary."""
    if watch:
        console.print("[bold yellow]Watching cluster health...[/]")
        try:
            while True:
                _run_analysis(namespace, describe)
                time.sleep(30)
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Stopped.[/]")
    else:
        _run_analysis(namespace, describe)


def _run_analysis(namespace: Optional[str], describe: bool):
    console.print("[dim]Collecting pod data...[/]")
    result = analyze(namespace, describe)
    console.print(Markdown(result))


if __name__ == "__main__":
    app()
