#!/usr/bin/env python3
"""
AI Perps Trader — Live Terminal Dashboard

Usage:
  python dashboard.py                  # auto-select markets
  python dashboard.py --portfolio 5000 # set account size
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual import work
from textual.widgets import DataTable, Footer, Static, Label
from textual.timer import Timer
from rich.text import Text
from rich.align import Align
from rich import box

from src.tools.hyperliquid_data import get_all_markets, get_markets
from src.tools.sentiment_data import get_fear_greed
from src.agents.market_selector import market_selector as _select_markets
from src.agents.funding_rate_analyst import funding_rate_analyst
from src.agents.oi_analyst import oi_analyst
from src.agents.technical_analyst import technical_analyst
from src.agents.sentiment_analyst import sentiment_analyst
from src.agents.risk_manager import risk_manager
from src.agents.portfolio_manager import portfolio_manager
from src.graph.state import AgentState

# ─── constants ───────────────────────────────────────────────────────────────

SPINNER = list("⣾⣽⣻⢿⡿⣟⣯⣷")
AGENT_LABELS = {
    "funding_rate_analyst": "Funding Rate",
    "oi_analyst":           "Open Interest",
    "technical_analyst":    "Technical",
    "sentiment_analyst":    "Sentiment",
}

# ─── CSS ─────────────────────────────────────────────────────────────────────

CSS = """
Screen {
    background: #0d1117;
    color: #c9d1d9;
    layers: base;
}

/* ── title bar ── */
#titlebar {
    height: 1;
    background: #161b22;
    color: #58a6ff;
    text-style: bold;
    content-align: center middle;
}
#statusbar {
    height: 1;
    background: #0d1117;
    color: #484f58;
    padding: 0 2;
    border-bottom: solid #21262d;
}

/* ── main split ── */
#main {
    height: 1fr;
    border-bottom: solid #21262d;
}
#scan-pane {
    width: 38%;
    border-right: solid #21262d;
}
#scan-title {
    height: 1;
    background: #161b22;
    color: #58a6ff;
    text-style: bold;
    padding: 0 1;
    border-bottom: solid #21262d;
}
#scan-table {
    height: 1fr;
    padding: 0 1;
}

/* ── right pane (analysts) ── */
#right-pane {
    width: 62%;
}
#analysts-title {
    height: 1;
    background: #161b22;
    color: #58a6ff;
    text-style: bold;
    padding: 0 1;
    border-bottom: solid #21262d;
}
#analyst-row-1, #analyst-row-2 {
    height: 1fr;
}
.analyst-card {
    width: 1fr;
    height: 1fr;
    border-right: solid #21262d;
    padding: 0 2;
    content-align: left top;
}
.analyst-card:last-of-type {
    border-right: none;
}
#analyst-row-1 {
    border-bottom: solid #21262d;
}

/* ── strategy ── */
#strategy {
    height: 2;
    padding: 0 2;
    border-bottom: solid #21262d;
    color: #8b949e;
}

/* ── decisions ── */
#decisions-title {
    height: 1;
    background: #161b22;
    color: #58a6ff;
    text-style: bold;
    padding: 0 1;
    border-bottom: solid #21262d;
}
#decisions-table {
    height: 1fr;
    padding: 0 1;
}

/* ── positions bar ── */
#positions {
    height: 1;
    background: #161b22;
    color: #484f58;
    padding: 0 2;
    border-top: solid #21262d;
}

Footer {
    background: #161b22;
    color: #484f58;
}
"""

# ─── widgets ─────────────────────────────────────────────────────────────────

class AnalystCard(Static):
    """Single analyst agent card with spinner → signal animation."""

    _spin_idx: int = 0
    _timer: Timer | None = None

    def __init__(self, agent_id: str, **kwargs) -> None:
        super().__init__("", **kwargs)
        self.agent_id = agent_id
        self.label = AGENT_LABELS.get(agent_id, agent_id)

    def on_mount(self) -> None:
        self._render("waiting", "", 0.0, "")

    def set_waiting(self) -> None:
        self._stop_timer()
        self._render("waiting", "", 0.0, "")

    def set_running(self) -> None:
        self._stop_timer()
        self._spin_idx = 0
        self._render("running", "", 0.0, "")
        self._timer = self.set_interval(0.08, self._tick)

    def set_done(self, signal: str, confidence: float, reasoning: str) -> None:
        self._stop_timer()
        self._render("done", signal, confidence, reasoning)

    def _tick(self) -> None:
        self._spin_idx += 1
        self._render("running", "", 0.0, "")

    def _stop_timer(self) -> None:
        if self._timer:
            self._timer.stop()
            self._timer = None

    def _render(self, status: str, signal: str, confidence: float, reasoning: str) -> None:
        label_txt = Text(f" {self.label} ", style="bold #484f58")

        if status == "waiting":
            body = Text("◌  waiting", style="#21262d")

        elif status == "running":
            frame = SPINNER[self._spin_idx % len(SPINNER)]
            body = Text(f"{frame}  analyzing...", style="bold #58a6ff")

        else:  # done
            color = {"bullish": "#3fb950", "bearish": "#f85149", "neutral": "#d29922"}.get(signal, "#c9d1d9")
            icon  = {"bullish": "▲", "bearish": "▼", "neutral": "◆"}.get(signal, "?")
            body  = Text()
            body.append(f"{icon}  {signal.upper()}", style=f"bold {color}")
            body.append(f"  {confidence:.0%}", style="#484f58")
            if reasoning:
                short = reasoning[:70] + ("…" if len(reasoning) > 70 else "")
                body.append(f"\n{short}", style="#484f58")

        out = Text()
        out.append_text(label_txt)
        out.append("\n")
        out.append_text(body)
        self.update(out)


# ─── main app ────────────────────────────────────────────────────────────────

class PerpsDashboard(App):
    CSS = CSS
    TITLE = "AI PERPS TRADER"
    BINDINGS = [
        Binding("r", "rerun", "Re-run", show=True),
        Binding("q", "quit",  "Quit",   show=True),
    ]

    def __init__(self, portfolio_value: float = 1000.0, markets: list[str] | None = None) -> None:
        super().__init__()
        self.portfolio_value = portfolio_value
        self.override_markets = markets or []
        self._selected_markets: list[str] = []

    # ── layout ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static(
            " ◈  AI PERPS TRADER  ◈  Claude · Phantom MCP · Hyperliquid",
            id="titlebar",
        )
        yield Static("initializing...", id="statusbar")

        with Horizontal(id="main"):
            with Vertical(id="scan-pane"):
                yield Static("  MARKET SCANNER", id="scan-title")
                yield DataTable(id="scan-table", show_header=True, cursor_type="none")

            with Vertical(id="right-pane"):
                yield Static("  ANALYST AGENTS", id="analysts-title")
                with Horizontal(id="analyst-row-1"):
                    yield AnalystCard("funding_rate_analyst", id="card-funding",   classes="analyst-card")
                    yield AnalystCard("oi_analyst",           id="card-oi",        classes="analyst-card")
                with Horizontal(id="analyst-row-2"):
                    yield AnalystCard("technical_analyst",    id="card-technical", classes="analyst-card")
                    yield AnalystCard("sentiment_analyst",    id="card-sentiment", classes="analyst-card")

        yield Static("", id="strategy")

        yield Static("  TRADE DECISIONS", id="decisions-title")
        yield DataTable(id="decisions-table", show_header=True, cursor_type="none")

        yield Static("  positions loading…", id="positions")
        yield Footer()

    def on_mount(self) -> None:
        # Scan table columns
        st = self.query_one("#scan-table", DataTable)
        st.add_columns("Market", "Price", "Funding 8h", "Vol/OI")

        # Decisions table columns
        dt = self.query_one("#decisions-table", DataTable)
        dt.add_columns("Market", "Action", "Size", "Lev", "Conf", "Reasoning")

        self._run_pipeline()

    # ── actions ─────────────────────────────────────────────────────────────

    def action_rerun(self) -> None:
        self.query_one("#scan-table", DataTable).clear()
        self.query_one("#decisions-table", DataTable).clear()
        self._selected_markets = []
        for card_id in ("card-funding", "card-oi", "card-technical", "card-sentiment"):
            self.query_one(f"#{card_id}", AnalystCard).set_waiting()
        self.query_one("#strategy", Static).update("")
        self.query_one("#positions", Static).update("  positions loading…")
        self._run_pipeline()

    # ── pipeline worker ──────────────────────────────────────────────────────

    @work(thread=True, exclusive=True)
    def _run_pipeline(self) -> None:
        try:
            self._pipeline()
        except Exception as e:
            self.call_from_thread(
                self.query_one("#statusbar", Static).update,
                Text(f"  ✗  error: {e}", style="bold #f85149"),
            )

    def _pipeline(self) -> None:
        cft = self.call_from_thread  # shorthand

        # ── 1. Fear & Greed + market scan ──
        cft(self._status, "scanning all Hyperliquid markets…")
        fng = get_fear_greed(3)
        fng_val   = int(fng[0]["value"]) if fng else 50
        fng_label = fng[0]["value_classification"] if fng else "Neutral"
        fng_trend = ""
        if len(fng) >= 2:
            d = int(fng[0]["value"]) - int(fng[-1]["value"])
            fng_trend = f" {'↑' if d > 0 else '↓'}{abs(d)}"

        fng_color = (
            "#f85149" if fng_val >= 75 else
            "#d29922" if fng_val >= 55 else
            "#c9d1d9" if fng_val >= 45 else
            "#3fb950" if fng_val >= 25 else "#58a6ff"
        )

        candidates = get_all_markets(min_volume_usd=500_000)[:40]
        cft(self._populate_scan, candidates)

        # ── 2. Select markets ──
        cft(self._status, "selecting markets…")
        initial: AgentState = {
            "markets": self.override_markets,
            "market_data": {}, "analyst_signals": [], "risk_limits": {},
            "trade_decisions": [], "portfolio_value": self.portfolio_value,
            "macro_context": {},
        }
        sel    = _select_markets(initial)
        selected = sel["markets"]
        macro    = sel["macro_context"]
        self._selected_markets = selected

        cft(self._highlight_selected, selected)

        regime       = macro.get("regime", "")
        regime_color = {"risk-on": "#3fb950", "risk-off": "#f85149", "neutral": "#d29922"}.get(regime, "#c9d1d9")

        title_txt = Text()
        title_txt.append(" ◈  AI PERPS TRADER  ◈  ", style="bold #58a6ff")
        title_txt.append(f"F&G {fng_val} {fng_label}{fng_trend}", style=f"bold {fng_color}")
        title_txt.append("   ")
        title_txt.append(f"REGIME: {regime.upper()}", style=f"bold {regime_color}")
        title_txt.append(f"   {datetime.now().strftime('%H:%M:%S')}", style="#484f58")
        cft(self.query_one("#titlebar", Static).update, title_txt)

        # ── 3. Fetch detailed market data ──
        cft(self._status, f"fetching data for {', '.join(selected)}…")
        market_data = get_markets(selected)

        state: AgentState = {
            "markets": selected, "market_data": market_data,
            "analyst_signals": [], "risk_limits": {},
            "trade_decisions": [], "portfolio_value": self.portfolio_value,
            "macro_context": macro,
        }

        # ── 4. Analysts ──
        all_signals = []
        for agent_id, card_id, fn in [
            ("funding_rate_analyst", "card-funding",   funding_rate_analyst),
            ("oi_analyst",           "card-oi",        oi_analyst),
            ("technical_analyst",    "card-technical", technical_analyst),
            ("sentiment_analyst",    "card-sentiment", sentiment_analyst),
        ]:
            cft(self._status, f"running {AGENT_LABELS[agent_id]}…")
            cft(self.query_one(f"#{card_id}", AnalystCard).set_running)

            result  = fn(state)
            signals = result["analyst_signals"]
            all_signals.extend(signals)

            # Aggregate per-card: majority signal among all selected markets
            if signals:
                counts  = {"bullish": 0, "bearish": 0, "neutral": 0}
                for s in signals:
                    counts[s["signal"]] += 1
                dominant = max(counts, key=counts.get)
                avg_conf = sum(s["confidence"] for s in signals) / len(signals)
                reasoning = next((s["reasoning"] for s in signals if s["signal"] == dominant), signals[0]["reasoning"])
            else:
                dominant, avg_conf, reasoning = "neutral", 0.0, ""

            cft(self.query_one(f"#{card_id}", AnalystCard).set_done, dominant, avg_conf, reasoning)

        state["analyst_signals"] = all_signals

        # ── 5. Risk manager ──
        cft(self._status, "calculating risk limits…")
        risk_result     = risk_manager(state)
        state["risk_limits"] = risk_result["risk_limits"]

        # ── 6. Portfolio strategy ──
        cft(self._status, "building portfolio strategy…")
        pm_result    = portfolio_manager(state)
        decisions    = pm_result["trade_decisions"]
        final_macro  = pm_result.get("macro_context", macro)
        strategy_txt = final_macro.get("strategy", "")

        cft(self._show_strategy, strategy_txt, final_macro)
        cft(self._show_decisions, decisions)

        # ── 7. Done ──
        ts = datetime.now().strftime("%H:%M:%S")
        cft(self._status, f"complete — {ts}  ·  press [r] to re-run")

    # ── UI update helpers ─────────────────────────────────────────────────────

    def _status(self, msg: str) -> None:
        self.query_one("#statusbar", Static).update(f"  {msg}")

    def _populate_scan(self, candidates: list[dict]) -> None:
        table = self.query_one("#scan-table", DataTable)
        for m in candidates:
            rate   = m["funding_rate_8h"]
            rate_c = "#3fb950" if rate < 0 else "#f85149" if rate > 0.0001 else "#484f58"
            vol_oi = m["volume_24h"] / m["open_interest"] if m["open_interest"] > 0 else 0
            sym_t  = Text(m["symbol"], style="#484f58")
            rate_t = Text(f"{rate*100:+.4f}%", style=rate_c)
            vol_t  = Text(f"{vol_oi:.2f}×", style="#484f58")
            price_t = Text(f"${m['price']:,.2f}", style="#484f58")
            table.add_row(sym_t, price_t, rate_t, vol_t, key=m["symbol"])

    def _highlight_selected(self, selected: list[str]) -> None:
        table = self.query_one("#scan-table", DataTable)
        for sym in selected:
            try:
                table.update_cell(sym, "Market", Text(f"● {sym}", style="bold #58a6ff"))
            except Exception:
                pass

    def _show_strategy(self, strategy: str, macro: dict) -> None:
        rationale = macro.get("selection_rationale", "")
        regime    = macro.get("regime", "neutral")
        regime_c  = {"risk-on": "#3fb950", "risk-off": "#f85149", "neutral": "#d29922"}.get(regime, "#c9d1d9")

        txt = Text()
        txt.append(f" {regime.upper()} ", style=f"bold {regime_c} on #161b22")
        txt.append("  ")
        short = strategy[:200] + ("…" if len(strategy) > 200 else "")
        txt.append(short, style="#8b949e")
        self.query_one("#strategy", Static).update(txt)

    def _show_decisions(self, decisions: list[dict]) -> None:
        table = self.query_one("#decisions-table", DataTable)
        table.clear()
        for d in decisions:
            action  = d["action"]
            color   = {"long": "#3fb950", "short": "#f85149", "flat": "#484f58"}.get(action, "#c9d1d9")
            icon    = {"long": "▲", "short": "▼", "flat": "─"}.get(action, " ")
            is_act  = action != "flat"

            sym_t    = Text(d["symbol"],              style="bold #58a6ff" if is_act else "#484f58")
            act_t    = Text(f"{icon} {action.upper()}", style=f"bold {color}")
            size_t   = Text(f"${d['size_usd']:.0f}" if is_act else "—",  style=color if is_act else "#21262d")
            lev_t    = Text(f"{d['leverage']:.0f}×"  if is_act else "—",  style=color if is_act else "#21262d")
            conf_t   = Text(f"{d['confidence']:.0%}", style="bold" if d["confidence"] >= 0.70 else "")
            reason   = d["reasoning"][:80] + ("…" if len(d["reasoning"]) > 80 else "")
            reason_t = Text(reason, style="#8b949e" if is_act else "#21262d")

            table.add_row(sym_t, act_t, size_t, lev_t, conf_t, reason_t)

        # Positions bar
        active = [d for d in decisions if d["action"] != "flat"]
        if active:
            pos_txt = Text("  TRADES: ", style="bold #484f58")
            for d in active:
                c = "#3fb950" if d["action"] == "long" else "#f85149"
                pos_txt.append(f"{d['symbol']} {d['action'].upper()} ${d['size_usd']:.0f} @ {d['leverage']:.0f}×  ", style=c)
        else:
            pos_txt = Text("  No active positions this cycle", style="#484f58")
        self.query_one("#positions", Static).update(pos_txt)


# ─── entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="AI Perps Trader Dashboard")
    p.add_argument("--portfolio", "-p", type=float, default=1000.0)
    p.add_argument("--markets",   "-m", default="",
                   help="Override market selection (comma-separated)")
    args = p.parse_args()

    markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()] if args.markets else None
    PerpsDashboard(portfolio_value=args.portfolio, markets=markets).run()


if __name__ == "__main__":
    main()
