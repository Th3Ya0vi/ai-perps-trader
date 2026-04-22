import os
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from src.graph.state import AgentState, TradeDecision
from src.utils import parse_json

_llm: ChatAnthropic | None = None

_CORRELATION_GROUPS = [
    ["BTC", "ETH"],
    ["SOL", "AVAX", "SUI", "APT", "TON", "TIA", "INJ", "SEI"],
    ["DOGE", "SHIB", "PEPE", "WIF", "BONK", "FLOKI", "NEIRO"],
    ["LINK", "UNI", "AAVE", "CRV", "SNX", "GMX", "PENDLE"],
    ["ARB", "OP", "MATIC", "STRK"],
    ["FET", "RENDER", "WLD", "TAO", "NEAR"],
]


def _get_llm() -> ChatAnthropic:
    global _llm
    if _llm is None:
        _llm = ChatAnthropic(model=os.getenv("MODEL", "claude-sonnet-4-6"), temperature=0)
    return _llm


def _correlation_group(symbol: str) -> str:
    for group in _CORRELATION_GROUPS:
        if symbol in group:
            return ", ".join(group)
    return "uncorrelated"


def portfolio_manager(state: AgentState) -> dict:
    """
    Portfolio strategist — builds a coherent, regime-aware portfolio.
    Considers signal alignment, correlation across positions, and macro context.
    Hard-enforces risk limits regardless of LLM output.
    """
    llm = _get_llm()
    all_signals = state["analyst_signals"]
    risk_limits = state["risk_limits"]
    macro = state.get("macro_context", {})
    fng_val = macro.get("fear_greed_value", 50)
    fng_label = macro.get("fear_greed_label", "Neutral")
    fng_trend = macro.get("fear_greed_trend", "")
    selection_rationale = macro.get("selection_rationale", "")

    # Reduce max exposure at sentiment extremes
    if fng_val >= 75 or fng_val <= 25:
        max_active_positions = 2
        exposure_note = "Sentiment extreme — cap at 2 positions, reduce size."
    elif fng_val >= 60 or fng_val <= 40:
        max_active_positions = 3
        exposure_note = "Elevated sentiment — cap at 3 positions."
    else:
        max_active_positions = 5
        exposure_note = "Neutral regime — up to 5 positions allowed."

    # Build per-symbol signal summaries
    per_market = {}
    for symbol in state["markets"]:
        syms = [s for s in all_signals if s["symbol"] == symbol]
        if not syms:
            continue
        bullish = [s for s in syms if s["signal"] == "bullish"]
        bearish = [s for s in syms if s["signal"] == "bearish"]
        per_market[symbol] = {
            "signals": syms,
            "bullish_count": len(bullish),
            "bearish_count": len(bearish),
            "avg_confidence": sum(s["confidence"] for s in syms) / len(syms),
            "correlation_group": _correlation_group(symbol),
            "limits": risk_limits.get(symbol, {"max_size_usd": 50, "max_leverage": 5}),
        }

    signals_block = ""
    for symbol, data in per_market.items():
        mkt = state["market_data"].get(symbol, {})
        limits = data["limits"]
        signals_block += f"\n{symbol} @ ${mkt.get('price', 0):,.2f} | group: {data['correlation_group']} | max ${limits['max_size_usd']:.0f} / {limits['max_leverage']}× lev\n"
        for s in data["signals"]:
            color = {"bullish": "▲", "bearish": "▼", "neutral": "◆"}[s["signal"]]
            signals_block += f"  {color} {s['agent']}: {s['signal'].upper()} ({s['confidence']:.0%}) — {s['reasoning'][:90]}\n"

    prompt = f"""You are the chief portfolio strategist for an AI perpetuals trading fund.

── MACRO CONTEXT ──────────────────────────────────────────
Fear & Greed: {fng_val} ({fng_label}{fng_trend})
{exposure_note}
Market selection rationale: {selection_rationale or 'N/A'}

── ANALYST SIGNALS ────────────────────────────────────────
{signals_block}
── PORTFOLIO STRATEGY RULES ───────────────────────────────
1. Only enter a position when ≥2 analysts agree AND avg confidence ≥ 0.60
2. Max {max_active_positions} active positions total
3. Max 1 position per correlation group (e.g. if long BTC, don't also long ETH)
4. Size: 40–60% of max_size_usd for moderate conviction (avg conf 0.60–0.74), 70–100% for high (≥0.75)
5. Leverage: 2–4× moderate, 5–8× strong signals, up to max only for exceptional alignment
6. Never exceed stated risk limits

First decide the overall strategy (risk-on / risk-off / neutral), then pick the best positions that fit.
Justify how the portfolio as a whole makes sense — not just each trade in isolation.

Respond with ONLY valid JSON, no markdown:
{{
  "strategy": "<2–3 sentences: overall regime read and portfolio approach>",
  "regime": "risk-on" | "risk-off" | "neutral",
  "decisions": [
    {{"symbol": "X", "action": "long"|"short"|"flat", "size_usd": <float>, "leverage": <float>, "confidence": <float>, "reasoning": "<1 sentence>"}},
    ...include ALL selected markets, even those returning flat...
  ]
}}"""

    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        data = parse_json(resp.content)

        strategy = data.get("strategy", "")
        regime = data.get("regime", "neutral")

        decisions: list[TradeDecision] = []
        for d in data.get("decisions", []):
            symbol = d["symbol"]
            limits = risk_limits.get(symbol, {"max_size_usd": 50, "max_leverage": 5})
            size = min(float(d.get("size_usd", 0)), limits["max_size_usd"])
            lev = min(float(d.get("leverage", 1)), float(limits["max_leverage"]))
            decisions.append(
                TradeDecision(
                    symbol=symbol,
                    action=d.get("action", "flat"),
                    size_usd=round(size, 2),
                    leverage=round(lev, 1),
                    confidence=float(d.get("confidence", 0)),
                    reasoning=d.get("reasoning", ""),
                )
            )

        # Ensure every selected market has a decision (default flat)
        decided = {d["symbol"] for d in decisions}
        for symbol in state["markets"]:
            if symbol not in decided:
                decisions.append(TradeDecision(
                    symbol=symbol, action="flat",
                    size_usd=0.0, leverage=1.0, confidence=0.0,
                    reasoning="Not included in portfolio strategy",
                ))

        return {
            "trade_decisions": decisions,
            "macro_context": {**macro, "strategy": strategy, "regime": regime},
        }

    except Exception as e:
        return {
            "trade_decisions": [
                TradeDecision(symbol=s, action="flat", size_usd=0.0,
                              leverage=1.0, confidence=0.0, reasoning=f"Error: {e}")
                for s in state["markets"]
            ]
        }
