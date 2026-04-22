from langgraph.graph import StateGraph, START, END

from src.graph.state import AgentState
from src.tools.hyperliquid_data import get_markets
from src.agents.market_selector import market_selector
from src.agents.funding_rate_analyst import funding_rate_analyst
from src.agents.oi_analyst import oi_analyst
from src.agents.technical_analyst import technical_analyst
from src.agents.sentiment_analyst import sentiment_analyst
from src.agents.risk_manager import risk_manager
from src.agents.portfolio_manager import portfolio_manager


def _fetch_market_data(state: AgentState) -> dict:
    return {"market_data": get_markets(state["markets"])}


def build_graph():
    """
    Pipeline:
      market_selector (auto-picks 5 markets OR respects CLI override)
        → fetch_market_data
          ├── funding_rate_analyst ─┐
          ├── oi_analyst            ├── risk_manager → portfolio_manager (strategist)
          ├── technical_analyst     │
          └── sentiment_analyst   ──┘
    """
    g = StateGraph(AgentState)

    g.add_node("market_selector", market_selector)
    g.add_node("fetch_market_data", _fetch_market_data)
    g.add_node("funding_rate_analyst", funding_rate_analyst)
    g.add_node("oi_analyst", oi_analyst)
    g.add_node("technical_analyst", technical_analyst)
    g.add_node("sentiment_analyst", sentiment_analyst)
    g.add_node("risk_manager", risk_manager)
    g.add_node("portfolio_manager", portfolio_manager)

    g.add_edge(START, "market_selector")
    g.add_edge("market_selector", "fetch_market_data")

    g.add_edge("fetch_market_data", "funding_rate_analyst")
    g.add_edge("fetch_market_data", "oi_analyst")
    g.add_edge("fetch_market_data", "technical_analyst")
    g.add_edge("fetch_market_data", "sentiment_analyst")

    g.add_edge("funding_rate_analyst", "risk_manager")
    g.add_edge("oi_analyst", "risk_manager")
    g.add_edge("technical_analyst", "risk_manager")
    g.add_edge("sentiment_analyst", "risk_manager")

    g.add_edge("risk_manager", "portfolio_manager")
    g.add_edge("portfolio_manager", END)

    return g.compile()


def run(markets: list[str] | None, portfolio_value: float = 1000.0) -> dict:
    graph = build_graph()
    result = graph.invoke(
        {
            "markets": markets or [],   # empty = auto-select
            "market_data": {},
            "analyst_signals": [],
            "risk_limits": {},
            "trade_decisions": [],
            "portfolio_value": portfolio_value,
            "macro_context": {},
        }
    )
    return {
        "decisions": result["trade_decisions"],
        "macro_context": result.get("macro_context", {}),
    }
