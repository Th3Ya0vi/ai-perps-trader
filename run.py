#!/usr/bin/env python3
"""
AI Perps Trader — CLI entrypoint

Usage:
  python run.py                              # auto-select 5 best markets
  python run.py --markets BTC,ETH,SOL       # override market selection
  python run.py --portfolio 5000            # set account size in USDC
  python run.py --output json               # machine-readable output

Decisions are saved to trade_decisions.json for Phantom MCP execution.
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

load_dotenv()

from src.main import run

console = Console()
DECISIONS_FILE = Path("trade_decisions.json")


def _action_style(action: str) -> str:
    return {
        "long":  "[bold green]LONG[/bold green]",
        "short": "[bold red]SHORT[/bold red]",
        "flat":  "[yellow]FLAT[/yellow]",
    }.get(action, action.upper())


def print_macro(macro: dict) -> None:
    fng_val = macro.get("fear_greed_value", "?")
    fng_label = macro.get("fear_greed_label", "")
    fng_trend = macro.get("fear_greed_trend", "")
    regime = macro.get("regime", "")
    strategy = macro.get("strategy", "")
    rationale = macro.get("selection_rationale", "")

    fng_color = (
        "bold red" if isinstance(fng_val, int) and fng_val >= 75
        else "red" if isinstance(fng_val, int) and fng_val >= 55
        else "yellow" if isinstance(fng_val, int) and fng_val >= 45
        else "green" if isinstance(fng_val, int) and fng_val >= 25
        else "bold green"
    )
    regime_color = {"risk-on": "green", "risk-off": "red", "neutral": "yellow"}.get(regime, "white")

    lines = []
    lines.append(f"[dim]Fear & Greed:[/dim] [{fng_color}]{fng_val} — {fng_label}{fng_trend}[/{fng_color}]")
    if regime:
        lines.append(f"[dim]Regime:[/dim]      [{regime_color}]{regime.upper()}[/{regime_color}]")
    if rationale:
        lines.append(f"[dim]Scan:[/dim]        {rationale}")
    if strategy:
        lines.append(f"[dim]Strategy:[/dim]    {strategy}")

    console.print(Panel("\n".join(lines), title="[bold]Market Context[/bold]", border_style="dim"))


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
            f"${d['size_usd']:.0f}" if is_active else "[dim]—[/dim]",
            f"{d['leverage']:.1f}×" if is_active else "[dim]—[/dim]",
            f"{d['confidence']:.0%}",
            d["reasoning"],
        )
    console.print(table)


def print_execution_hint(decisions: list[dict]) -> None:
    active = [d for d in decisions if d["action"] != "flat"]
    if not active:
        console.print("\n[dim]No trades to execute (all flat).[/dim]")
        return
    console.print("\n[bold]To execute via Phantom MCP, ask Claude:[/bold]")
    for d in active:
        color = "green" if d["action"] == "long" else "red"
        console.print(
            f"  • Open a [{color}]{d['action']}[/{color}] on {d['symbol']} "
            f"for ${d['size_usd']:.0f} at {d['leverage']:.1f}× leverage"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="AI multi-agent perps trader")
    parser.add_argument("--markets", "-m", default="",
                        help="Comma-separated symbols to analyze (default: auto-select)")
    parser.add_argument("--portfolio", "-p", type=float, default=1000.0,
                        help="Portfolio value in USDC (default: 1000)")
    parser.add_argument("--output", "-o", choices=["table", "json"], default="table")
    args = parser.parse_args()

    markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()] if args.markets else None
    mode = f"Manual: {', '.join(markets)}" if markets else "Auto-select from all Hyperliquid markets"

    console.print(f"\n[bold cyan]AI Perps Trader[/bold cyan]")
    console.print(f"Mode     : {mode}")
    console.print(f"Portfolio: ${args.portfolio:,.2f} USDC\n")

    with console.status("[bold green]Running pipeline…"):
        result = run(markets, args.portfolio)

    decisions = result["decisions"]
    macro = result["macro_context"]

    if args.output == "json":
        print(json.dumps({"macro_context": macro, "decisions": decisions}, indent=2))
    else:
        print_macro(macro)
        console.print()
        print_table(decisions)
        print_execution_hint(decisions)

    DECISIONS_FILE.write_text(json.dumps({"macro_context": macro, "decisions": decisions}, indent=2))
    console.print(f"\n[dim]Saved to {DECISIONS_FILE}[/dim]\n")


if __name__ == "__main__":
    main()
