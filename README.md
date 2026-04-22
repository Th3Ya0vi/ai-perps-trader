# AI Perps Trader

A multi-agent AI system for perpetuals trading on [Hyperliquid](https://hyperliquid.xyz), executed via [Phantom](https://phantom.com) MCP. Inspired by [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund), rebuilt for crypto perps.

Four independent analyst agents run in parallel on live market data, vote on direction, and a portfolio manager synthesizes their signals into sized trade decisions. Execution is handled by Phantom MCP — one command to go from signal to on-chain position.

## Demo

**Trade decisions table**

![Trade Decisions](assets/demo_decisions.svg)

**Per-market analyst breakdown**

![Analyst Signals](assets/demo_signals.svg)

## Architecture

```
fetch_market_data  (Hyperliquid REST)
  ├── funding_rate_analyst   contrarian: extreme funding = crowded side, fade it
  ├── oi_analyst             conviction: rising OI + price = new money entering
  ├── technical_analyst      RSI · EMA crossover · Bollinger Bands (1h candles)
  └── sentiment_analyst      Fear & Greed · CoinGecko votes · Polymarket odds
          ↓  (signals accumulate via LangGraph reducer)
      risk_manager           hard caps: max position size · max leverage · % of account
          ↓
      portfolio_manager      acts only when ≥2 analysts agree at ≥60% avg confidence
          ↓
      trade_decisions.json → Phantom MCP → Hyperliquid
```

Built with [LangGraph](https://github.com/langchain-ai/langgraph) for orchestration, [Claude](https://anthropic.com) as the LLM backbone, and the [Phantom MCP](https://phantom.com) for execution.

## Quickstart

**Requirements:** Python 3.11+, [Phantom](https://phantom.com) wallet with USDC in the perps account

```bash
git clone https://github.com/Th3Ya0vi/ai-perps-trader
cd ai-perps-trader
python -m venv .venv && source .venv/bin/activate
pip install langgraph langchain-anthropic langchain-core httpx python-dotenv rich pydantic
cp .env.example .env   # add your ANTHROPIC_API_KEY
```

**Run analysis:**

```bash
python run.py                              # BTC, ETH, SOL
python run.py --markets BTC,ETH,SOL,WIF   # custom markets
python run.py --portfolio 5000            # set account size
python run.py --output json               # machine-readable
```

**Execute via Phantom MCP (inside a Claude Code session):**

After `run.py` writes `trade_decisions.json`, tell Claude:
> "Execute the trades in trade_decisions.json"

Claude reads the file and calls `perps_open` for each non-flat decision.

**Automate with a loop (Claude Code):**

```
/loop 15m Run the AI perps trader pipeline and execute any new trade decisions via Phantom MCP
```

## Risk Controls

Set in `.env` before going live:

| Variable | Default | Description |
|---|---|---|
| `MAX_POSITION_SIZE_USD` | 200 | Hard USD cap per position |
| `MAX_LEVERAGE` | 10 | Absolute leverage ceiling |
| `MAX_ACCOUNT_RISK_PCT` | 0.05 | Max % of account per position |

The portfolio manager also enforces its own rules: no trade unless ≥2 analysts agree and average confidence ≥ 60%. Risk limits are re-applied as a hard ceiling on the LLM's output regardless of its recommendation.

## Analyst Agents

| Agent | Signal type | Data source |
|---|---|---|
| Funding Rate | Contrarian — high positive funding = crowded longs = bearish | Hyperliquid REST |
| Open Interest | Directional — rising OI + price = new conviction | Hyperliquid REST |
| Technical | Momentum/mean-reversion — RSI, EMA cross, Bollinger | Hyperliquid candles |
| Sentiment | Macro context — Fear & Greed, community votes, prediction markets | alternative.me · CoinGecko · Polymarket |

## Adding Markets

Pass any Hyperliquid perp symbol via `--markets`:

```bash
python run.py --markets WIF,PEPE,HYPE,TIA
```

CoinGecko sentiment is supported for the most common symbols. To add a new one, update `_CG_IDS` in `src/tools/sentiment_data.py`.

## Stack

- **Orchestration:** LangGraph
- **LLM:** Claude Sonnet (Anthropic)
- **Market data:** Hyperliquid REST API
- **Sentiment data:** alternative.me · CoinGecko · Polymarket Gamma API
- **Execution:** Phantom MCP → Hyperliquid perps

## Disclaimer

This is experimental software. It trades real money. Use small position sizes while testing. Not financial advice.
