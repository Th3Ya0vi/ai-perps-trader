#!/usr/bin/env python3
"""Generates assets/demo_analysis.svg and assets/demo_signals.svg for the README."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich import box
from src.main import run

os.makedirs("assets", exist_ok=True)

MARKETS = ["BTC", "ETH", "SOL"]
PORTFOLIO = 1000.0

print("Running pipeline (this takes ~30s)…")
decisions = run(MARKETS, PORTFOLIO)

# ── Screenshot 1: Trade decisions table ───────────────────────────────────────
c1 = Console(record=True, width=110)

c1.print()
c1.print("[bold cyan]  AI Perps Trader[/bold cyan]   [dim]powered by Claude + Phantom MCP[/dim]")
c1.print(f"  [dim]Markets: {', '.join(MARKETS)}   Portfolio: ${PORTFOLIO:,.0f} USDC[/dim]")
c1.print()

table = Table(show_lines=True, border_style="cyan", box=box.ROUNDED, padding=(0, 1))
table.add_column("Market", style="bold cyan", no_wrap=True, width=8)
table.add_column("Action", width=8)
table.add_column("Size", justify="right", width=10)
table.add_column("Leverage", justify="right", width=10)
table.add_column("Confidence", justify="right", width=12)
table.add_column("Reasoning", min_width=50)

for d in decisions:
    color = {"long": "green", "short": "red", "flat": "yellow"}[d["action"]]
    table.add_row(
        d["symbol"],
        f"[bold {color}]{d['action'].upper()}[/bold {color}]",
        f"${d['size_usd']:.0f}" if d["action"] != "flat" else "[dim]—[/dim]",
        f"{d['leverage']:.1f}×" if d["action"] != "flat" else "[dim]—[/dim]",
        f"[bold]{d['confidence']:.0%}[/bold]",
        d["reasoning"][:120] + ("…" if len(d["reasoning"]) > 120 else ""),
    )

c1.print(table)
c1.print()
c1.save_svg("assets/demo_decisions.svg", title="AI Perps Trader — Trade Decisions")
print("Saved assets/demo_decisions.svg")

# ── Screenshot 2: Analyst signal breakdown ────────────────────────────────────
from src.graph.state import AgentState
from src.tools.hyperliquid_data import get_markets
from src.agents.funding_rate_analyst import funding_rate_analyst
from src.agents.oi_analyst import oi_analyst
from src.agents.technical_analyst import technical_analyst
from src.agents.sentiment_analyst import sentiment_analyst

print("Fetching analyst breakdown…")
market_data = get_markets(MARKETS)
base_state: AgentState = {
    "markets": MARKETS, "market_data": market_data,
    "analyst_signals": [], "risk_limits": {}, "trade_decisions": [],
    "portfolio_value": PORTFOLIO,
}
all_signals = []
for fn in [funding_rate_analyst, oi_analyst, technical_analyst, sentiment_analyst]:
    all_signals.extend(fn(base_state)["analyst_signals"])

c2 = Console(record=True, width=110)
c2.print()
c2.print("[bold cyan]  AI Perps Trader[/bold cyan]   [dim]Analyst Signal Breakdown[/dim]")
c2.print()

AGENT_LABELS = {
    "funding_rate_analyst": "Funding Rate",
    "oi_analyst":           "Open Interest",
    "technical_analyst":    "Technical",
    "sentiment_analyst":    "Sentiment",
}

for symbol in MARKETS:
    syms = [s for s in all_signals if s["symbol"] == symbol]
    mkt = market_data.get(symbol, {})
    price = mkt.get("price", 0)

    t = Table(
        title=f"[bold cyan]{symbol}[/bold cyan]  [dim]${price:,.2f}[/dim]",
        show_lines=True, border_style="dim", box=box.SIMPLE_HEAVY, padding=(0, 1),
    )
    t.add_column("Analyst", style="dim", width=16)
    t.add_column("Signal", width=10)
    t.add_column("Conf", justify="right", width=7)
    t.add_column("Reasoning", min_width=60)

    for s in syms:
        color = {"bullish": "green", "bearish": "red", "neutral": "yellow"}[s["signal"]]
        t.add_row(
            AGENT_LABELS.get(s["agent"], s["agent"]),
            f"[bold {color}]{s['signal'].upper()}[/bold {color}]",
            f"{s['confidence']:.0%}",
            s["reasoning"][:100] + ("…" if len(s["reasoning"]) > 100 else ""),
        )
    c2.print(t)
    c2.print()

c2.save_svg("assets/demo_signals.svg", title="AI Perps Trader — Analyst Breakdown")
print("Saved assets/demo_signals.svg")
print("Done.")
