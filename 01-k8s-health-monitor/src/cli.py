"""CLI entry point for the K8s health monitor agent.

Usage:
    python -m 01-k8s-health-monitor.src.cli
    python -m 01-k8s-health-monitor.src.cli --namespace default
    python -m 01-k8s-health-monitor.src.cli --scenario crash
    python -m 01-k8s-health-monitor.src.cli --scenario healthy
    python -m 01-k8s-health-monitor.src.cli --scenario two-bad
    python -m 01-k8s-health-monitor.src.cli --watch
"""

import time

import typer
from rich.console import Console
from rich.markdown import Markdown

from .agent import analyze_with_alerts
from .k8s_client import set_scenario

app = typer.Typer(
    name="k8s-health",
    help="Monitor your Kubernetes cluster and get plain-English pod health summaries.",
)
console = Console()

SCENARIO_HELP = (
    "Mock scenario when no cluster is available. "
    "Default: 'composite' (dynamic mix of 2-3 bad pods). "
    "General: 'healthy', 'crashing', 'mixed'. "
    "Solo (1 bad pod): 'solo-crashloop', 'solo-error', 'solo-imagepull', 'solo-pending', 'solo-oom'."
)


@app.command()
def health(
    namespace: str | None = typer.Option(None, "--namespace", "-n", help="Filter to a specific namespace."),
    scenario: str = typer.Option(
        "composite",
        "--scenario",
        "-s",
        help=SCENARIO_HELP,
    ),
    watch: bool = typer.Option(
        False,
        "--watch",
        "-w",
        help="Continuously monitor and re-analyze every 30 seconds.",
    ),
):
    """Analyze pod health and return a plain-English summary."""
    set_scenario(scenario)

    if watch:
        console.print("[bold yellow]Watching cluster health...[/]")
        try:
            while True:
                _run_analysis(namespace)
                time.sleep(30)
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Stopped.[/]")
    else:
        _run_analysis(namespace)


def _run_analysis(namespace: str | None):
    console.print("[dim]Investigating cluster...[/]")
    result = analyze_with_alerts(namespace)
    console.print(Markdown(result))


if __name__ == "__main__":
    app()
