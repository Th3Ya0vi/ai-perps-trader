#!/usr/bin/env python3
"""Generates SVG screenshots for the README using live pipeline output."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from src.main import run
from src.graph.state import AgentState
from src.tools.hyperliquid_data import get_markets
from src.agents.market_selector import market_selector
from src.agents.funding_rate_analyst import funding_rate_analyst
from src.agents.oi_analyst import oi_analyst
from src.agents.technical_analyst import technical_analyst
from src.agents.sentiment_analyst import sentiment_analyst

os.makedirs("assets", exist_ok=True)
PORTFOLIO = 1000.0

AGENT_LABELS = {
    "funding_rate_analyst": "Funding Rate",
    "oi_analyst":           "Open Interest",
    "technical_analyst":    "Technical",
    "sentiment_analyst":    "Sentiment",
}

# ── Run full autonomous pipeline ──────────────────────────────────────────────
print("Running autonomous pipeline…")
result = run(None, PORTFOLIO)
decisions = result["decisions"]
macro = result["macro_context"]
selected_markets = [d["symbol"] for d in decisions]

# ── Screenshot 1: Market context + trade decisions ────────────────────────────
c1 = Console(record=True, width=114)
c1.print()
c1.print("[bold cyan]  AI Perps Trader[/bold cyan]   [dim]powered by Claude · Phantom MCP · Hyperliquid[/dim]")
c1.print()

fng_val = macro.get("fear_greed_value", 50)
fng_label = macro.get("fear_greed_label", "")
fng_trend = macro.get("fear_greed_trend", "")
regime = macro.get("regime", "")
strategy = macro.get("strategy", "")
rationale = macro.get("selection_rationale", "")

fng_color = (
    "bold red" if fng_val >= 75 else "red" if fng_val >= 55
    else "yellow" if fng_val >= 45 else "green" if fng_val >= 25
    else "bold green"
)
regime_color = {"risk-on": "green", "risk-off": "red", "neutral": "yellow"}.get(regime, "white")

ctx_lines = [
    f"[dim]Fear & Greed :[/dim]  [{fng_color}]{fng_val} — {fng_label}{fng_trend}[/{fng_color}]",
    f"[dim]Regime       :[/dim]  [{regime_color}]{regime.upper()}[/{regime_color}]",
]
if rationale:
    ctx_lines.append(f"[dim]Market scan  :[/dim]  {rationale[:160]}{'…' if len(rationale) > 160 else ''}")
if strategy:
    ctx_lines.append(f"[dim]Strategy     :[/dim]  {strategy[:200]}{'…' if len(strategy) > 200 else ''}")
c1.print(Panel("\n".join(ctx_lines), title="[bold]Market Context[/bold]", border_style="dim", padding=(0, 1)))
c1.print()

table = Table(show_lines=True, border_style="cyan", box=box.ROUNDED, padding=(0, 1))
table.add_column("Market", style="bold cyan", no_wrap=True, width=8)
table.add_column("Action", width=8)
table.add_column("Size", justify="right", width=10)
table.add_column("Leverage", justify="right", width=10)
table.add_column("Conf", justify="right", width=7)
table.add_column("Reasoning", min_width=55)

for d in decisions:
    color = {"long": "green", "short": "red", "flat": "yellow"}[d["action"]]
    is_active = d["action"] != "flat"
    table.add_row(
        d["symbol"],
        f"[bold {color}]{d['action'].upper()}[/bold {color}]",
        f"${d['size_usd']:.0f}" if is_active else "[dim]—[/dim]",
        f"{d['leverage']:.1f}×" if is_active else "[dim]—[/dim]",
        f"[bold]{d['confidence']:.0%}[/bold]",
        d["reasoning"][:130] + ("…" if len(d["reasoning"]) > 130 else ""),
    )

c1.print(table)
c1.print()
c1.save_svg("assets/demo_decisions.svg", title="AI Perps Trader — Autonomous Trade Decisions")
print("Saved assets/demo_decisions.svg")

# ── Screenshot 2: Per-market analyst breakdown ────────────────────────────────
print("Fetching analyst breakdown…")
market_data = get_markets(selected_markets)
base_state: AgentState = {
    "markets": selected_markets,
    "market_data": market_data,
    "analyst_signals": [],
    "risk_limits": {},
    "trade_decisions": [],
    "portfolio_value": PORTFOLIO,
    "macro_context": macro,
}
all_signals = []
for fn in [funding_rate_analyst, oi_analyst, technical_analyst, sentiment_analyst]:
    all_signals.extend(fn(base_state)["analyst_signals"])

c2 = Console(record=True, width=114)
c2.print()
c2.print("[bold cyan]  AI Perps Trader[/bold cyan]   [dim]Analyst Signal Breakdown[/dim]")
c2.print()

active_markets = [d["symbol"] for d in decisions if d["action"] != "flat"]
all_markets_ordered = active_markets + [d["symbol"] for d in decisions if d["action"] == "flat"]

for symbol in all_markets_ordered:
    decision = next((d for d in decisions if d["symbol"] == symbol), None)
    syms = [s for s in all_signals if s["symbol"] == symbol]
    mkt = market_data.get(symbol, {})
    price = mkt.get("price", 0)

    action_str = ""
    if decision:
        color = {"long": "green", "short": "red", "flat": "yellow"}[decision["action"]]
        action_str = f"  [bold {color}]→ {decision['action'].upper()}[/bold {color}]"

    t = Table(
        title=f"[bold cyan]{symbol}[/bold cyan]  [dim]${price:,.2f}[/dim]{action_str}",
        show_lines=True, border_style="dim", box=box.SIMPLE_HEAVY, padding=(0, 1),
    )
    t.add_column("Analyst", style="dim", width=14)
    t.add_column("Signal", width=10)
    t.add_column("Conf", justify="right", width=7)
    t.add_column("Reasoning", min_width=65)

    for s in syms:
        sig_color = {"bullish": "green", "bearish": "red", "neutral": "yellow"}[s["signal"]]
        t.add_row(
            AGENT_LABELS.get(s["agent"], s["agent"]),
            f"[bold {sig_color}]{s['signal'].upper()}[/bold {sig_color}]",
            f"{s['confidence']:.0%}",
            s["reasoning"][:110] + ("…" if len(s["reasoning"]) > 110 else ""),
        )

    c2.print(t)
    c2.print()

c2.save_svg("assets/demo_signals.svg", title="AI Perps Trader — Analyst Breakdown")
print("Saved assets/demo_signals.svg")
print("Done.")
