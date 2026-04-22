import json
import os
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from src.graph.state import AgentState, AnalystSignal
from src.tools.hyperliquid_data import (
    get_candles,
    compute_rsi,
    compute_ema,
    compute_bollinger_bands,
)

_llm: ChatAnthropic | None = None


def _get_llm() -> ChatAnthropic:
    global _llm
    if _llm is None:
        _llm = ChatAnthropic(model=os.getenv("MODEL", "claude-sonnet-4-6"), temperature=0)
    return _llm


def technical_analyst(state: AgentState) -> dict:
    """RSI, EMA crossover, and Bollinger Band signals on 1h candles."""
    llm = _get_llm()
    signals: list[AnalystSignal] = []

    for symbol in state["markets"]:
        mkt = state["market_data"].get(symbol)
        if not mkt:
            continue

        candles = get_candles(symbol, interval="1h", lookback_hours=72)
        closes = [c["c"] for c in candles]
        price = mkt["price"]

        rsi = compute_rsi(closes)
        ema20 = compute_ema(closes, 20)
        ema50 = compute_ema(closes, 50)
        bb_mid, bb_upper, bb_lower = compute_bollinger_bands(closes)
        bb_pct = (
            (price - bb_lower) / (bb_upper - bb_lower) * 100
            if bb_upper != bb_lower
            else 50.0
        )

        prompt = f"""You are a crypto technical analyst specializing in perpetuals.

Market: {symbol}
Price: ${price:,.2f}
RSI (14h): {rsi:.1f}
EMA20: ${ema20:,.2f}  (price {'above' if price > ema20 else 'below'})
EMA50: ${ema50:,.2f}  (price {'above' if price > ema50 else 'below'})
EMA trend: {'bullish (EMA20 > EMA50)' if ema20 > ema50 else 'bearish (EMA20 < EMA50)'}
Bollinger Band %: {bb_pct:.1f}  (0 = lower band, 100 = upper band)
BB lower: ${bb_lower:,.2f}  |  mid: ${bb_mid:,.2f}  |  upper: ${bb_upper:,.2f}

Interpretation:
• RSI > 70: overbought  |  RSI < 30: oversold
• Price above both EMAs with EMA20 > EMA50: uptrend
• Price below both EMAs with EMA20 < EMA50: downtrend
• BB% > 80: near upper band, stretched  |  BB% < 20: near lower band, oversold
• Weight the confluence of all signals, not any one indicator in isolation

Respond with ONLY valid JSON, no markdown fences:
{{"signal": "bullish" | "bearish" | "neutral", "confidence": <0.0–1.0>, "reasoning": "<1–2 sentences>"}}"""

        try:
            resp = llm.invoke([HumanMessage(content=prompt)])
            data = json.loads(resp.content.strip())
            signals.append(
                AnalystSignal(
                    agent="technical_analyst",
                    symbol=symbol,
                    signal=data["signal"],
                    confidence=float(data["confidence"]),
                    reasoning=data["reasoning"],
                )
            )
        except Exception as e:
            signals.append(
                AnalystSignal(
                    agent="technical_analyst",
                    symbol=symbol,
                    signal="neutral",
                    confidence=0.0,
                    reasoning=f"Error: {e}",
                )
            )

    return {"analyst_signals": signals}
