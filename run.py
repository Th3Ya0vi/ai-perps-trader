#!/usr/bin/env python3
"""
AI Perps Trader — CLI entrypoint

Usage:
  python run.py                              # analyze BTC, ETH, SOL
  python run.py --markets BTC,ETH,SOL,WIF   # custom markets
  python run.py --portfolio 5000            # set account size
  python run.py --output json               # machine-readable output

After analysis, decisions are saved to trade_decisions.json.
To execute via Phantom MCP, run this inside a Claude Code session and
Claude will read the JSON and call perps_open for each non-flat decision.
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()

from src.main import run

console = Console()
DECISIONS_FILE = Path("trade_decisions.json")


def _action_style(action: str) -> str:
    return {"long": "[bold green]LONG[/bold green]",
            "short": "[bold red]SHORT[/bold red]",
            "flat": "[yellow]FLAT[/yellow]"}.get(action, action.upper())


def print_table(decisions: list[dict]) -> None:
    table = Table(title="Trade Decisions", show_lines=True, border_style="cyan")
    table.add_column("Market", style="cyan", no_wrap=True)
    table.add_column("Action")
    table.add_column("Size (USD)", justify="right")
    table.add_column("Leverage", justify="right")
    table.add_column("Confidence", justify="right")
    table.add_column("Reasoning", max_width=60)

    for d in decisions:
        is_active = d["action"] != "flat"
        table.add_row(
            d["symbol"],
            _action_style(d["action"]),
            f"${d['size_usd']:.0f}" if is_active else "—",
            f"{d['leverage']:.1f}×" if is_active else "—",
            f"{d['confidence']:.0%}",
            d["reasoning"],
        )

    console.print(table)


def print_phantom_commands(decisions: list[dict]) -> None:
    active = [d for d in decisions if d["action"] != "flat"]
    if not active:
        console.print("\n[dim]No trades to execute (all flat).[/dim]")
        return

    console.print("\n[bold]To execute via Phantom MCP, ask Claude:[/bold]")
    for d in active:
        console.print(
            f"  • Open a [{'green' if d['action'] == 'long' else 'red'}]{d['action']}[/] "
            f"on {d['symbol']} for ${d['size_usd']:.0f} at {d['leverage']:.1f}× leverage"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="AI multi-agent perps trader")
    parser.add_argument("--markets", "-m", default="BTC,ETH,SOL",
                        help="Comma-separated market symbols (default: BTC,ETH,SOL)")
    parser.add_argument("--portfolio", "-p", type=float, default=1000.0,
                        help="Portfolio value in USDC (default: 1000)")
    parser.add_argument("--output", "-o", choices=["table", "json"], default="table",
                        help="Output format (default: table)")
    args = parser.parse_args()

    markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()]
    if not markets:
        console.print("[red]No markets specified.[/red]")
        sys.exit(1)

    console.print(f"\n[bold cyan]AI Perps Trader[/bold cyan]")
    console.print(f"Markets  : {', '.join(markets)}")
    console.print(f"Portfolio: ${args.portfolio:,.2f} USDC\n")

    with console.status("[bold green]Running analyst pipeline…"):
        decisions = run(markets, args.portfolio)

    if args.output == "json":
        print(json.dumps(decisions, indent=2))
    else:
        print_table(decisions)
        print_phantom_commands(decisions)

    DECISIONS_FILE.write_text(json.dumps(decisions, indent=2))
    console.print(f"\n[dim]Saved to {DECISIONS_FILE} for Phantom MCP execution.[/dim]\n")


if __name__ == "__main__":
    main()
