from typing import TypedDict, Annotated
import operator


class AnalystSignal(TypedDict):
    agent: str
    symbol: str
    signal: str  # "bullish" | "bearish" | "neutral"
    confidence: float  # 0.0 - 1.0
    reasoning: str


class TradeDecision(TypedDict):
    symbol: str
    action: str  # "long" | "short" | "flat"
    size_usd: float
    leverage: float
    confidence: float
    reasoning: str


class AgentState(TypedDict):
    markets: list[str]
    market_data: dict                                           # symbol → market snapshot
    analyst_signals: Annotated[list[AnalystSignal], operator.add]  # accumulates across analyst nodes
    risk_limits: dict                                          # symbol → {max_size_usd, max_leverage}
    trade_decisions: list[TradeDecision]
    portfolio_value: float                                     # total USDC in perps account
