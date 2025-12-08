"""주문 생성/체결을 담당하는 실행 엔진."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable

from upbit_bot.adapters.upbit import OrderSide, UpbitClient
from upbit_bot.risk.engine import RiskEngine

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    order_uuid: str
    market: str
    side: str
    price: float
    volume: float


class ExecutionEngine:
    def __init__(self, client: UpbitClient | None = None, risk_engine: RiskEngine | None = None):
        self.client = client or UpbitClient()
        self.risk_engine = risk_engine

    def _tick_size(self, price: float) -> float:
        if price < 10:
            return 0.01
        if price < 100:
            return 0.1
        if price < 1000:
            return 1
        if price < 10000:
            return 5
        if price < 50000:
            return 10
        if price < 100000:
            return 50
        if price < 500000:
            return 100
        if price < 1000000:
            return 500
        if price < 2000000:
            return 1000
        return 2000

    def align_price(self, price: float) -> float:
        tick = self._tick_size(price)
        return round(price / tick) * tick

    async def build_order(self, market: str, side: str, entry: float, stop: float, cash_available: float) -> tuple[float, float]:
        """틱 사이즈, 최소 주문금액, 리스크를 반영한 주문 가격/수량 계산."""

        if not self.risk_engine:
            raise RuntimeError("RiskEngine이 필요합니다")

        chance = await self.client.order_chance(market)
        min_total = max(30000.0, float(chance.get("market", {}).get("bid", {}).get("min_total", 0)))
        fee = float(chance["bid_fee"] if side == "buy" else chance["ask_fee"])

        price = self.align_price(entry)
        volume = self.risk_engine.position_size(price, stop)

        order_value = price * volume * (1 + fee)
        if order_value < min_total:
            volume = min_total / price
            order_value = price * volume * (1 + fee)

        if order_value > cash_available:
            volume = cash_available / (price * (1 + fee))

        return price, max(volume, 0.0)

    async def submit_limit_order(self, market: str, side: str, price: float, volume: float) -> ExecutionResult:
        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        response = await self.client.place_order(market, order_side, volume=volume, price=price)
        logger.info("주문 전송 완료 %s %s @ %s", market, side, price)
        return ExecutionResult(
            order_uuid=response.get("uuid", ""),
            market=market,
            side=side,
            price=price,
            volume=volume,
        )

    def size_with_risk(self, entry: float, stop: float) -> float:
        if not self.risk_engine:
            return 0.0
        return self.risk_engine.position_size(entry, stop)
