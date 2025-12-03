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
