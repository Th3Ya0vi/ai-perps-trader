import json
import os
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from src.graph.state import AgentState, TradeDecision

_llm: ChatAnthropic | None = None


def _get_llm() -> ChatAnthropic:
    global _llm
    if _llm is None:
        _llm = ChatAnthropic(model=os.getenv("MODEL", "claude-sonnet-4-6"), temperature=0)
    return _llm


def portfolio_manager(state: AgentState) -> dict:
    """
    Synthesizes all analyst signals into final trade decisions.
    Only acts when 2+ analysts agree AND combined confidence is high enough.
    """
    llm = _get_llm()
    decisions: list[TradeDecision] = []
    all_signals = state["analyst_signals"]

    for symbol in state["markets"]:
        mkt = state["market_data"].get(symbol)
        if not mkt:
            continue

        limits = state["risk_limits"].get(symbol, {"max_size_usd": 50.0, "max_leverage": 3})
        symbol_signals = [s for s in all_signals if s["symbol"] == symbol]

        if not symbol_signals:
            decisions.append(
                TradeDecision(
                    symbol=symbol,
                    action="flat",
                    size_usd=0.0,
                    leverage=1.0,
                    confidence=0.0,
                    reasoning="No analyst signals available",
                )
            )
            continue

        signals_block = "\n".join(
            f"  • {s['agent']}: {s['signal'].upper()} "
            f"(confidence {s['confidence']:.0%}) — {s['reasoning']}"
            for s in symbol_signals
        )

        prompt = f"""You are the portfolio manager for an AI perpetuals trading fund.
Make the final trade decision for {symbol}.

Market: {symbol} @ ${mkt['price']:,.2f}
Account USDC: ${state['portfolio_value']:,.2f}
Risk limits: max size ${limits['max_size_usd']:.0f} | max leverage {limits['max_leverage']}x

Analyst signals:
{signals_block}

Decision rules:
1. Only trade when ≥2 analysts agree on direction AND average confidence ≥ 0.6
2. Size: use 40–80% of max_size_usd for moderate conviction, 80–100% for high conviction (avg conf ≥ 0.75)
3. Leverage: 2–3x for moderate, 4–6x for strong, up to max only on exceptional alignment
4. Return action="flat", size_usd=0, leverage=1 if signals are mixed or low confidence
5. NEVER exceed the stated risk limits

Respond with ONLY valid JSON, no markdown fences:
{{"action": "long" | "short" | "flat", "size_usd": <float>, "leverage": <float>, "confidence": <0.0–1.0>, "reasoning": "<1–2 sentences>"}}"""

        try:
            resp = llm.invoke([HumanMessage(content=prompt)])
            data = json.loads(resp.content.strip())
            action = data["action"]
            size = float(data["size_usd"])
            lev = float(data["leverage"])

            # Hard-enforce risk limits regardless of LLM output
            size = min(size, limits["max_size_usd"])
            lev = min(lev, float(limits["max_leverage"]))

            decisions.append(
                TradeDecision(
                    symbol=symbol,
                    action=action,
                    size_usd=round(size, 2),
                    leverage=round(lev, 1),
                    confidence=float(data["confidence"]),
                    reasoning=data["reasoning"],
                )
            )
        except Exception as e:
            decisions.append(
                TradeDecision(
                    symbol=symbol,
                    action="flat",
                    size_usd=0.0,
                    leverage=1.0,
                    confidence=0.0,
                    reasoning=f"Error: {e}",
                )
            )

    return {"trade_decisions": decisions}
