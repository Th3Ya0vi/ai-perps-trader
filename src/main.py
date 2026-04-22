from langgraph.graph import StateGraph, START, END

from src.graph.state import AgentState
from src.tools.hyperliquid_data import get_markets
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
      fetch_data
        ├── funding_rate_analyst ─┐
        ├── oi_analyst            ├── risk_manager → portfolio_manager
        └── technical_analyst  ──┘

    Analyst nodes run sequentially in sync mode; analyst_signals accumulates
    via the operator.add reducer so risk_manager sees all signals at once.
    """
    g = StateGraph(AgentState)

    g.add_node("fetch_market_data", _fetch_market_data)
    g.add_node("funding_rate_analyst", funding_rate_analyst)
    g.add_node("oi_analyst", oi_analyst)
    g.add_node("technical_analyst", technical_analyst)
    g.add_node("sentiment_analyst", sentiment_analyst)
    g.add_node("risk_manager", risk_manager)
    g.add_node("portfolio_manager", portfolio_manager)

    g.add_edge(START, "fetch_market_data")

    # Fan-out to analysts
    g.add_edge("fetch_market_data", "funding_rate_analyst")
    g.add_edge("fetch_market_data", "oi_analyst")
    g.add_edge("fetch_market_data", "technical_analyst")
    g.add_edge("fetch_market_data", "sentiment_analyst")

    # Fan-in: risk_manager waits for all four analysts
    g.add_edge("funding_rate_analyst", "risk_manager")
    g.add_edge("oi_analyst", "risk_manager")
    g.add_edge("technical_analyst", "risk_manager")
    g.add_edge("sentiment_analyst", "risk_manager")

    g.add_edge("risk_manager", "portfolio_manager")
    g.add_edge("portfolio_manager", END)

    return g.compile()


def run(markets: list[str], portfolio_value: float = 1000.0) -> list[dict]:
    graph = build_graph()
    result = graph.invoke(
        {
            "markets": markets,
            "market_data": {},
            "analyst_signals": [],
            "risk_limits": {},
            "trade_decisions": [],
            "portfolio_value": portfolio_value,
        }
    )
    return result["trade_decisions"]
