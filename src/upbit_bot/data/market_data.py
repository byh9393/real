"""마켓 데이터 수집 및 캐시 레이어."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

from upbit_bot.adapters.upbit import UpbitClient, Candle
from upbit_bot.config import get_settings


class MarketUniverse:
    """거래 가능한 KRW 마켓 리스트를 관리한다."""

    def __init__(self, client: UpbitClient | None = None):
        self.client = client or UpbitClient()

    async def fetch_krw_markets(self) -> list[str]:
        markets = await self.client.list_markets(is_details=True)
        krw = [m["market"] for m in markets if m["market"].startswith("KRW-") and not m.get("market_warning")]
        return sorted(krw)


class CandleCache:
    """OHLCV를 주기적으로 디스크에 캐시하여 백테스트 및 고속 조회에 사용한다."""

    def __init__(self, base_dir: str | Path | None = None, client: UpbitClient | None = None):
        settings = get_settings()
        self.base_dir = Path(base_dir or settings.backtest_data_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.client = client or UpbitClient()

    def _path(self, market: str, unit: int) -> Path:
        return self.base_dir / f"{market}_m{unit}.parquet"

    async def refresh(self, market: str, unit: int = 1, count: int = 200) -> pd.DataFrame:
        candles = await self.client.candles(market, unit=unit, count=count)
        frame = _candles_to_df(candles)
        frame.to_parquet(self._path(market, unit), index=False)
        return frame

    def load(self, market: str, unit: int = 1) -> pd.DataFrame:
        path = self._path(market, unit)
        if not path.exists():
            raise FileNotFoundError(f"캐시가 없습니다: {path}")
        return pd.read_parquet(path)


def _candles_to_df(candles: list[Candle]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "market": c.market,
                "timestamp": datetime.fromtimestamp(c.timestamp / 1000),
                "open": c.opening_price,
                "high": c.high_price,
                "low": c.low_price,
                "close": c.trade_price,
            }
            for c in candles
        ]
    ).sort_values("timestamp")
