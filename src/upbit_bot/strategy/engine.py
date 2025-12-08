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
    take_profit: float
    trailing: float


@dataclass
class PositionSnapshot:
    market: str
    side: str
    entry_price: float
    volume: float
    stop: float
    take_profit: float
    trailing: float


class StrategyEngine:
    """EMA, RSI, MACD, 변동성 지표를 결합한 신호 엔진."""

    def __init__(self):
        self.indicator_windows = {"ema_fast": 21, "ema_slow": 55, "rsi": 14}

    def _rsi(self, close: pd.Series, window: int) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = -delta.clip(upper=0).rolling(window).mean()
        rs = gain / loss.replace(0, float("inf"))
        return 100 - (100 / (1 + rs))

    def _atr(self, frame: pd.DataFrame, window: int = 14) -> pd.Series:
        high_low = frame["high"] - frame["low"]
        high_close = (frame["high"] - frame["close"].shift()).abs()
        low_close = (frame["low"] - frame["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window).mean()

    def _macd(self, close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
        ema_fast = close.ewm(span=12).mean()
        ema_slow = close.ewm(span=26).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=9).mean()
        hist = macd - signal
        return macd, signal, hist

    def score_market(self, candles: pd.DataFrame) -> float:
        if len(candles) < 60:
            return 0.0

        close = candles["close"]
        volume = candles["volume"].fillna(method="ffill").fillna(0)

        ema_fast = close.ewm(span=self.indicator_windows["ema_fast"]).mean()
        ema_slow = close.ewm(span=self.indicator_windows["ema_slow"]).mean()
        macd, _, hist = self._macd(close)
        rsi = self._rsi(close, self.indicator_windows["rsi"])
        atr = self._atr(candles)

        trend_score = (ema_fast.iloc[-1] - ema_slow.iloc[-1]) / close.iloc[-1]
        momentum_score = (close.iloc[-1] / close.iloc[-10]) - 1
        volume_score = (volume.iloc[-1] / (volume.rolling(30).mean().iloc[-1] or 1)) - 1
        quality = 1 if atr.iloc[-1] > 0 else 0

        macd_bias = hist.iloc[-1]
        rsi_bias = (rsi.iloc[-1] - 50) / 50

        return float((trend_score * 0.35 + momentum_score * 0.25 + macd_bias * 0.2 + rsi_bias * 0.1 + volume_score * 0.1) * quality)

    def generate_entry_signal(self, market: str, candles: pd.DataFrame) -> Signal | None:
        score = self.score_market(candles)
        if score == 0:
            return None

        close = candles["close"].iloc[-1]
        atr = self._atr(candles).iloc[-1]

        if score > 0:
            stop = max(close - atr * 2, close * 0.97)
            take_profit = close + atr * 3
            return Signal(
                market=market,
                side="buy",
                score=score,
                entry=close,
                stop=stop,
                take_profit=take_profit,
                trailing=atr * 1.5,
            )

        stop = min(close + atr * 2, close * 1.03)
        take_profit = close - atr * 3
        return Signal(
            market=market,
            side="sell",
            score=score,
            entry=close,
            stop=stop,
            take_profit=take_profit,
            trailing=atr * 1.5,
        )

    def should_exit(self, candles: pd.DataFrame, position: PositionSnapshot) -> bool:
        """손절·익절·모멘텀 둔화 조건을 모두 확인."""

        close = candles["close"].iloc[-1]
        atr = self._atr(candles).iloc[-1]
        macd, _, hist = self._macd(candles["close"])
        rsi = self._rsi(candles["close"], self.indicator_windows["rsi"])

        if position.side == "buy":
            trailing_stop = max(position.stop, close - position.trailing)
            if close <= trailing_stop or close <= position.stop:
                return True
            if close >= position.take_profit:
                return True
            if hist.iloc[-1] < 0 and rsi.iloc[-1] < 45:
                return True
            if atr > 0 and (close - position.entry_price) / atr < -1:
                return True
            return False

        trailing_stop = min(position.stop, close + position.trailing)
        if close >= trailing_stop or close >= position.stop:
            return True
        if close <= position.take_profit:
            return True
        if hist.iloc[-1] > 0 and rsi.iloc[-1] > 55:
            return True
        if atr > 0 and (position.entry_price - close) / atr < -1:
            return True
        return False
