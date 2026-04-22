import time
import httpx
from typing import Any

_HL_URL = "https://api.hyperliquid.xyz/info"


def _post(payload: dict) -> Any:
    with httpx.Client(timeout=15) as client:
        r = client.post(_HL_URL, json=payload)
        r.raise_for_status()
        return r.json()


def get_markets(symbols: list[str]) -> dict:
    """Fetch current price, funding rate, OI, and volume for requested symbols."""
    data = _post({"type": "metaAndAssetCtxs"})
    meta_universe, ctxs = data[0]["universe"], data[1]

    result = {}
    for asset_meta, ctx in zip(meta_universe, ctxs):
        name = asset_meta["name"]
        if name not in symbols:
            continue
        result[name] = {
            "symbol": name,
            "price": float(ctx["markPx"]),
            "funding_rate_8h": float(ctx["funding"]),
            "open_interest": float(ctx["openInterest"]),
            "volume_24h": float(ctx.get("dayNtlVlm", 0)),
            "max_leverage": int(asset_meta.get("maxLeverage", 20)),
        }
    return result


def get_candles(symbol: str, interval: str = "1h", lookback_hours: int = 72) -> list[dict]:
    """Fetch OHLCV candles from Hyperliquid."""
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - lookback_hours * 3_600_000
    data = _post({
        "type": "candleSnapshot",
        "req": {
            "coin": symbol,
            "interval": interval,
            "startTime": start_ms,
            "endTime": now_ms,
        },
    })
    return [
        {
            "t": c["t"],
            "o": float(c["o"]),
            "h": float(c["h"]),
            "l": float(c["l"]),
            "c": float(c["c"]),
            "v": float(c["v"]),
        }
        for c in data
    ]


def compute_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    avg_gain = sum(d for d in deltas[-period:] if d > 0) / period
    avg_loss = sum(-d for d in deltas[-period:] if d < 0) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def compute_ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    k = 2.0 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1.0 - k)
    return ema


def compute_bollinger_bands(closes: list[float], period: int = 20) -> tuple[float, float, float]:
    if len(closes) < period:
        mid = closes[-1] if closes else 0.0
        return mid, mid * 1.02, mid * 0.98
    recent = closes[-period:]
    mid = sum(recent) / period
    std = (sum((c - mid) ** 2 for c in recent) / period) ** 0.5
    return mid, mid + 2.0 * std, mid - 2.0 * std
