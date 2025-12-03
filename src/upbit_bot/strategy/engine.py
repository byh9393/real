"""다중 지표 기반 스코어링 및 진입/청산 신호 엔진."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass
class Signal:
    market: str
    side: str  # "buy" or "sell"
    score: float
    entry: float
    stop: float


class StrategyEngine:
    """지표 조합을 통해 시장별 스코어를 생성한다."""

    def __init__(self):
        self.indicator_windows = {"ema_fast": 20, "ema_slow": 60}

    def score_market(self, candles: pd.DataFrame) -> float:
        if candles.empty:
            return 0.0
        close = candles["close"]
        ema_fast = close.ewm(span=self.indicator_windows["ema_fast"]).mean()
        ema_slow = close.ewm(span=self.indicator_windows["ema_slow"]).mean()
        momentum = (close.iloc[-1] - close.iloc[-10]) / close.iloc[-10]
        trend = ema_fast.iloc[-1] - ema_slow.iloc[-1]
        return float(trend * 0.7 + momentum * 0.3)

    def generate_signal(self, market: str, candles: pd.DataFrame) -> Signal | None:
        score = self.score_market(candles)
        if score > 0:
            entry = candles["close"].iloc[-1]
            stop = entry * 0.97
            return Signal(market=market, side="buy", score=score, entry=entry, stop=stop)
        if score < 0:
            entry = candles["close"].iloc[-1]
            stop = entry * 1.03
            return Signal(market=market, side="sell", score=score, entry=entry, stop=stop)
        return None
