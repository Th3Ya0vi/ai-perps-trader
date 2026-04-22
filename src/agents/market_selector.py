import json
from src.utils import parse_json
import os
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from src.graph.state import AgentState
from src.tools.hyperliquid_data import get_all_markets
from src.tools.sentiment_data import get_fear_greed

_llm: ChatAnthropic | None = None

# Known correlated groups — used in the selection prompt so Claude is aware
_CORRELATION_GROUPS = {
    "large_cap": ["BTC", "ETH"],
    "l1_alts": ["SOL", "AVAX", "SUI", "APT", "TON", "TIA", "INJ", "SEI"],
    "memes": ["DOGE", "SHIB", "PEPE", "WIF", "BONK", "FLOKI", "NEIRO"],
    "defi": ["LINK", "UNI", "AAVE", "CRV", "SNX", "GMX", "PENDLE"],
    "l2": ["ARB", "OP", "MATIC", "STRK", "MANTA"],
    "ai": ["FET", "RENDER", "WLD", "TAO", "NEAR"],
}


def _get_llm() -> ChatAnthropic:
    global _llm
    if _llm is None:
        _llm = ChatAnthropic(model=os.getenv("MODEL", "claude-sonnet-4-6"), temperature=0)
    return _llm


def market_selector(state: AgentState) -> dict:
    """
    If markets are already set (CLI override), just fetch macro context and return.
    Otherwise, scan all Hyperliquid markets and select the 5-7 best opportunities.
    """
    fng = get_fear_greed(3)
    fng_latest = fng[0] if fng else {"value": "50", "value_classification": "Neutral"}
    fng_trend = ""
    if len(fng) >= 2:
        delta = int(fng[0]["value"]) - int(fng[-1]["value"])
        fng_trend = f", {'rising' if delta > 0 else 'falling'} {abs(delta)} pts"

    macro_context = {
        "fear_greed_value": int(fng_latest["value"]),
        "fear_greed_label": fng_latest["value_classification"],
        "fear_greed_trend": fng_trend,
        "selection_rationale": "",
    }

    # If markets were pre-specified via CLI, skip auto-selection
    if state.get("markets"):
        return {"macro_context": macro_context}

    llm = _get_llm()
    candidates = get_all_markets(min_volume_usd=500_000)[:40]  # top 40 by volume

    fng_val = int(fng_latest["value"])
    if fng_val >= 75:
        regime_note = "Extreme Greed — reduce overall exposure, prefer short setups or very high-conviction longs only."
    elif fng_val >= 55:
        regime_note = "Greed — be selective, favor quality assets, avoid chasing momentum."
    elif fng_val >= 45:
        regime_note = "Neutral — balanced approach, look for directional setups with strong signal alignment."
    elif fng_val >= 25:
        regime_note = "Fear — look for oversold quality assets, strong long setups in resilient names."
    else:
        regime_note = "Extreme Fear — high-conviction contrarian longs in top-tier assets, or short weak alts."

    candidates_text = "\n".join(
        f"  {m['symbol']:<8} price=${m['price']:>12,.2f}  "
        f"funding(8h)={m['funding_rate_8h'] * 100:>+.4f}%  "
        f"OI=${m['open_interest']:>12,.0f}  "
        f"vol24h=${m['volume_24h']:>12,.0f}"
        for m in candidates
    )

    groups_text = "\n".join(
        f"  {group}: {', '.join(members)}"
        for group, members in _CORRELATION_GROUPS.items()
    )

    prompt = f"""You are a crypto quant scanning perpetuals markets for today's best trading opportunities.

Fear & Greed: {fng_latest['value']} ({fng_latest['value_classification']}{fng_trend})
Regime guidance: {regime_note}

Known correlation groups (avoid over-concentrating):
{groups_text}

All liquid Hyperliquid markets (filtered ≥$500K daily volume, sorted by volume):
{candidates_text}

Select exactly 5 markets to deep-analyze. Prioritize:
1. Extreme funding rates (high absolute value = crowded positioning = alpha opportunity)
2. Volume spikes relative to OI (unusual activity often precedes a move)
3. Diversification across correlation groups — don't select 3 assets from the same group
4. Regime fit — in Fear, favor quality; in Greed, consider shorts on overextended names

Respond with ONLY valid JSON, no markdown:
{{"selected": ["SYM1", "SYM2", "SYM3", "SYM4", "SYM5"], "rationale": "<2 sentences on why these markets>"}}"""

    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        data = parse_json(resp.content)
        selected = [s.upper() for s in data["selected"]][:7]
        macro_context["selection_rationale"] = data.get("rationale", "")
    except Exception:
        # Fall back to top 5 by volume if LLM fails
        selected = [m["symbol"] for m in candidates[:5]]

    return {
        "markets": selected,
        "macro_context": macro_context,
    }
