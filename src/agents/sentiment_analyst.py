import json
import os
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from src.graph.state import AgentState, AnalystSignal
from src.tools.sentiment_data import (
    get_fear_greed,
    get_coingecko_sentiment,
    get_polymarket_crypto_markets,
)

_llm: ChatAnthropic | None = None


def _get_llm() -> ChatAnthropic:
    global _llm
    if _llm is None:
        _llm = ChatAnthropic(model=os.getenv("MODEL", "claude-sonnet-4-6"), temperature=0)
    return _llm


def _fng_summary(readings: list[dict]) -> str:
    if not readings:
        return "unavailable"
    latest = readings[0]
    trend = ""
    if len(readings) >= 2:
        delta = int(readings[0]["value"]) - int(readings[-1]["value"])
        trend = f", trending {'up' if delta > 0 else 'down'} {abs(delta)} pts over {len(readings)} readings"
    return f"{latest['value']} / 100 ({latest['value_classification']}{trend})"


def _poly_summary(markets: list[dict]) -> str:
    if not markets:
        return "No relevant markets found."
    lines = []
    for m in markets[:5]:
        prob = f"{m['yes_probability']}% YES" if m["yes_probability"] is not None else "N/A"
        lines.append(f"  • [{prob}] {m['question']}")
    return "\n".join(lines)


def sentiment_analyst(state: AgentState) -> dict:
    """
    Synthesizes Fear & Greed index, CoinGecko community sentiment,
    and Polymarket prediction market odds into a directional signal.

    F&G is contrarian at extremes; CoinGecko votes and Polymarket odds
    are directional (high bullish votes / high YES price = bullish).
    """
    llm = _get_llm()

    # Fetch once — shared across all symbols
    fng = get_fear_greed(3)
    fng_text = _fng_summary(fng)

    signals: list[AnalystSignal] = []

    for symbol in state["markets"]:
        mkt = state["market_data"].get(symbol)
        if not mkt:
            continue

        cg = get_coingecko_sentiment(symbol)
        poly = get_polymarket_crypto_markets(limit=5, search=symbol)
        poly_text = _poly_summary(poly)

        cg_block = "unavailable"
        if cg:
            cg_block = (
                f"  Community bullish votes: {cg['sentiment_votes_up_pct']:.1f}%"
                if cg.get("sentiment_votes_up_pct") is not None
                else "  Community votes: N/A"
            )
            if cg.get("price_change_24h_pct") is not None:
                cg_block += f"\n  24h price change: {cg['price_change_24h_pct']:+.2f}%"
            if cg.get("price_change_7d_pct") is not None:
                cg_block += f"\n  7d price change: {cg['price_change_7d_pct']:+.2f}%"

        prompt = f"""You are a crypto market sentiment analyst specializing in perpetuals.

Market: {symbol} @ ${mkt['price']:,.2f}

--- Fear & Greed Index (market-wide) ---
Current: {fng_text}
Scale: 0 = Extreme Fear, 100 = Extreme Greed
Contrarian lens: Extreme Fear (<20) → potential bottoms, Extreme Greed (>80) → potential tops.
Momentum lens: rising F&G = improving sentiment, falling F&G = deteriorating.

--- CoinGecko Community Sentiment ---
{cg_block}
High bullish vote % (>70%) = community is positioned bullish.
Low vote % (<40%) or falling = community skepticism / capitulation signal.

--- Polymarket Prediction Markets (relevant to {symbol}) ---
{poly_text}
High YES probability on bullish events = market expects upside.
Low YES probability = market skeptical / pricing in downside.

Synthesize all three sources into a single directional signal.
Weight: F&G is market-wide context; CoinGecko and Polymarket are coin-specific.
A divergence (e.g., F&G = Fear but coin community = 85% bullish) suggests resilient sentiment.

Respond with ONLY valid JSON, no markdown fences:
{{"signal": "bullish" | "bearish" | "neutral", "confidence": <0.0–1.0>, "reasoning": "<1–2 sentences>"}}"""

        try:
            resp = llm.invoke([HumanMessage(content=prompt)])
            data = json.loads(resp.content.strip())
            signals.append(
                AnalystSignal(
                    agent="sentiment_analyst",
                    symbol=symbol,
                    signal=data["signal"],
                    confidence=float(data["confidence"]),
                    reasoning=data["reasoning"],
                )
            )
        except Exception as e:
            signals.append(
                AnalystSignal(
                    agent="sentiment_analyst",
                    symbol=symbol,
                    signal="neutral",
                    confidence=0.0,
                    reasoning=f"Error: {e}",
                )
            )

    return {"analyst_signals": signals}
