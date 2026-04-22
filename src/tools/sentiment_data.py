import httpx
from typing import Any

# CoinGecko IDs for common Hyperliquid perp symbols
_CG_IDS: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "AVAX": "avalanche-2",
    "DOGE": "dogecoin",
    "WIF": "dogwifhat",
    "PEPE": "pepe",
    "ARB": "arbitrum",
    "OP": "optimism",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "AAVE": "aave",
    "SUI": "sui",
    "APT": "aptos",
    "INJ": "injective-protocol",
    "TIA": "celestia",
    "HYPE": "hyperliquid",
}


def _get(url: str, params: dict | None = None, timeout: int = 10) -> Any:
    with httpx.Client(timeout=timeout) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        return r.json()


def get_fear_greed(limit: int = 3) -> list[dict]:
    """
    Returns the last `limit` Fear & Greed readings (most recent first).
    Each entry: {value: str, value_classification: str, timestamp: str}
    Scale: 0 = Extreme Fear, 100 = Extreme Greed.
    Contrarian signal: extremes predict reversals.
    """
    data = _get("https://api.alternative.me/fng/", params={"limit": limit})
    return data.get("data", [])


def get_coingecko_sentiment(symbol: str) -> dict | None:
    """
    Returns community sentiment and market momentum from CoinGecko.
    Returns None if symbol is not mapped or request fails.
    """
    cg_id = _CG_IDS.get(symbol.upper())
    if not cg_id:
        return None
    try:
        data = _get(
            f"https://api.coingecko.com/api/v3/coins/{cg_id}",
            params={
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "true",
                "developer_data": "false",
                "sparkline": "false",
            },
        )
        mkt = data.get("market_data", {})
        community = data.get("community_data", {})
        return {
            "sentiment_votes_up_pct": data.get("sentiment_votes_up_percentage"),
            "sentiment_votes_down_pct": data.get("sentiment_votes_down_percentage"),
            "price_change_24h_pct": mkt.get("price_change_percentage_24h"),
            "price_change_7d_pct": mkt.get("price_change_percentage_7d"),
            "market_cap_rank": data.get("market_cap_rank"),
            "twitter_followers": community.get("twitter_followers"),
            "reddit_avg_posts_48h": community.get("reddit_average_posts_48h"),
            "reddit_avg_comments_48h": community.get("reddit_average_comments_48h"),
        }
    except Exception:
        return None


def get_polymarket_crypto_markets(limit: int = 8, search: str | None = None) -> list[dict]:
    """
    Returns top open Polymarket prediction markets related to crypto.
    Pass `search` to filter by symbol name (e.g. "bitcoin", "ethereum").
    Each entry includes the question, YES probability, and volume.
    """
    _SYMBOL_SEARCH = {
        "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
        "BNB": "bnb", "AVAX": "avalanche", "DOGE": "dogecoin",
        "WIF": "wif", "PEPE": "pepe", "ARB": "arbitrum",
        "LINK": "chainlink", "SUI": "sui", "APT": "aptos",
    }
    query = _SYMBOL_SEARCH.get(search.upper(), search.lower()) if search else None
    try:
        params: dict = {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "order": "volume",
            "ascending": "false",
        }
        if query:
            params["search"] = query
        else:
            params["tag_slug"] = "crypto"
        data = _get("https://gamma-api.polymarket.com/markets", params=params)
        markets = []
        for m in data if isinstance(data, list) else []:
            outcomes = m.get("outcomes", "[]")
            prices = m.get("outcomePrices", "[]")
            # outcomes and outcomePrices may be JSON strings
            if isinstance(outcomes, str):
                import json
                try:
                    outcomes = json.loads(outcomes)
                    prices = json.loads(prices)
                except Exception:
                    outcomes, prices = [], []

            yes_prob = None
            if outcomes and prices:
                for outcome, price in zip(outcomes, prices):
                    if str(outcome).lower() == "yes":
                        try:
                            yes_prob = round(float(price) * 100, 1)
                        except Exception:
                            pass

            markets.append({
                "question": m.get("question", ""),
                "yes_probability": yes_prob,
                "volume_usd": m.get("volume"),
                "end_date": m.get("endDate", ""),
            })
        return markets
    except Exception:
        return []
