import json
import os
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from src.graph.state import AgentState, AnalystSignal

_ANNUALIZED = 3 * 365  # 3 eight-hour periods/day × 365 days

_llm: ChatAnthropic | None = None


def _get_llm() -> ChatAnthropic:
    global _llm
    if _llm is None:
        _llm = ChatAnthropic(model=os.getenv("MODEL", "claude-sonnet-4-6"), temperature=0)
    return _llm


def funding_rate_analyst(state: AgentState) -> dict:
    """
    Contrarian signal: extreme positive funding → crowded longs → bearish.
    Extreme negative funding → crowded shorts → bullish.
    """
    llm = _get_llm()
    signals: list[AnalystSignal] = []

    for symbol in state["markets"]:
        mkt = state["market_data"].get(symbol)
        if not mkt:
            continue

        rate_8h = mkt["funding_rate_8h"]
        rate_ann = rate_8h * _ANNUALIZED

        prompt = f"""You are a crypto perpetuals funding rate analyst.

Market: {symbol}
Price: ${mkt['price']:,.2f}
Funding rate (8h): {rate_8h:.6f}  ({rate_8h * 100:.4f}%)
Funding rate (annualized): {rate_ann:.2%}
Open interest: ${mkt['open_interest']:,.0f}
24h volume: ${mkt['volume_24h']:,.0f}

Funding rate is a contrarian signal — longs pay shorts when positive:
• Ann. > +100%: extreme crowding of longs → strong bearish
• Ann. +30–100%: crowded longs → moderate bearish
• Ann. −10% to +30%: neutral / normal carry
• Ann. −30% to −10%: crowded shorts → moderate bullish
• Ann. < −30%: extreme crowding of shorts → strong bullish

Weight: high OI amplifies the signal. Strong trending price may sustain elevated funding.

Respond with ONLY valid JSON, no markdown fences:
{{"signal": "bullish" | "bearish" | "neutral", "confidence": <0.0–1.0>, "reasoning": "<1–2 sentences>"}}"""

        try:
            resp = llm.invoke([HumanMessage(content=prompt)])
            data = json.loads(resp.content.strip())
            signals.append(
                AnalystSignal(
                    agent="funding_rate_analyst",
                    symbol=symbol,
                    signal=data["signal"],
                    confidence=float(data["confidence"]),
                    reasoning=data["reasoning"],
                )
            )
        except Exception as e:
            signals.append(
                AnalystSignal(
                    agent="funding_rate_analyst",
                    symbol=symbol,
                    signal="neutral",
                    confidence=0.0,
                    reasoning=f"Error: {e}",
                )
            )

    return {"analyst_signals": signals}
