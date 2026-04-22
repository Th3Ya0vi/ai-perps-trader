import os

from src.graph.state import AgentState

_MAX_POSITION_USD = float(os.getenv("MAX_POSITION_SIZE_USD", "200"))
_MAX_LEVERAGE = int(os.getenv("MAX_LEVERAGE", "10"))
_MAX_RISK_PCT = float(os.getenv("MAX_ACCOUNT_RISK_PCT", "0.05"))


def risk_manager(state: AgentState) -> dict:
    """
    Computes per-symbol risk limits before the portfolio manager sizes positions.
    Hard caps: absolute USD limit AND % of account, whichever is smaller.
    Leverage is capped at both the env config and the market's own maximum.
    """
    portfolio_value = state["portfolio_value"]
    risk_limits: dict = {}

    for symbol in state["markets"]:
        mkt = state["market_data"].get(symbol)
        if not mkt:
            continue

        account_limit = portfolio_value * _MAX_RISK_PCT
        max_size = min(_MAX_POSITION_USD, account_limit)

        market_max_lev = mkt.get("max_leverage", 20)
        max_lev = min(_MAX_LEVERAGE, market_max_lev)

        risk_limits[symbol] = {
            "max_size_usd": round(max_size, 2),
            "max_leverage": max_lev,
        }

    return {"risk_limits": risk_limits}
