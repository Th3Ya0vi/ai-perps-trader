import json
import os
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from src.graph.state import AgentState, AnalystSignal
from src.tools.hyperliquid_data import get_candles

_llm: ChatAnthropic | None = None


def _get_llm() -> ChatAnthropic:
    global _llm
    if _llm is None:
        _llm = ChatAnthropic(model=os.getenv("MODEL", "claude-sonnet-4-6"), temperature=0)
    return _llm


def oi_analyst(state: AgentState) -> dict:
    """
    Signal derived from open interest vs price direction divergence.
    Rising OI + rising price = new conviction longs (bullish).
    Rising OI + falling price = new conviction shorts (bearish).
    High OI/volume ratio = stretched positioning, mean-reversion risk.
    """
    llm = _get_llm()
    signals: list[AnalystSignal] = []

    for symbol in state["markets"]:
        mkt = state["market_data"].get(symbol)
        if not mkt:
            continue

        candles = get_candles(symbol, interval="4h", lookback_hours=48)
        if len(candles) >= 6:
            price_24h_ago = candles[-6]["c"]
        elif candles:
            price_24h_ago = candles[0]["c"]
        else:
            price_24h_ago = mkt["price"]

        price_change_pct = (mkt["price"] - price_24h_ago) / price_24h_ago * 100
        oi = mkt["open_interest"]
        vol = mkt["volume_24h"]
        oi_vol_ratio = oi / vol if vol > 0 else 0.0

        prompt = f"""You are a crypto perpetuals open-interest analyst.

Market: {symbol}
Price: ${mkt['price']:,.2f}
24h price change: {price_change_pct:+.2f}%
Open interest: ${oi:,.0f}
24h volume: ${vol:,.0f}
OI / Volume ratio: {oi_vol_ratio:.2f}x

OI interpretation:
• Rising price + rising OI → new longs entering, bullish conviction
• Falling price + rising OI → new shorts entering, bearish conviction
• Rising price + falling OI → short squeeze (bullish, but less durable)
• Falling price + falling OI → long capitulation (bearish, but less durable)
• OI/Vol > 3× → positions stretched vs activity → elevated mean-reversion risk
• OI/Vol < 0.5× → high turnover, trending environment

Respond with ONLY valid JSON, no markdown fences:
{{"signal": "bullish" | "bearish" | "neutral", "confidence": <0.0–1.0>, "reasoning": "<1–2 sentences>"}}"""

        try:
            resp = llm.invoke([HumanMessage(content=prompt)])
            data = json.loads(resp.content.strip())
            signals.append(
                AnalystSignal(
                    agent="oi_analyst",
                    symbol=symbol,
                    signal=data["signal"],
                    confidence=float(data["confidence"]),
                    reasoning=data["reasoning"],
                )
            )
        except Exception as e:
            signals.append(
                AnalystSignal(
                    agent="oi_analyst",
                    symbol=symbol,
                    signal="neutral",
                    confidence=0.0,
                    reasoning=f"Error: {e}",
                )
            )

    return {"analyst_signals": signals}
