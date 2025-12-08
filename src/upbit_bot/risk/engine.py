"""리스크 관리 및 자금 배분 로직."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class RiskLimits:
    per_trade_risk_pct: float = 0.01
    daily_loss_limit_pct: float = 0.03
    max_position_pct: float = 0.1
    max_total_exposure_pct: float = 1.0
    max_positions: int = 10


class RiskEngine:
    """리스크 한도 계산과 포지션 사이징을 담당."""

    def __init__(self, equity_provider: Callable[[], float]):
        self.equity_provider = equity_provider
        self.limits = RiskLimits()
        self.daily_loss = 0.0

    def reset_daily(self) -> None:
        self.daily_loss = 0.0

    def can_open_new_position(self, market: str, open_positions: dict[str, float]) -> bool:
        equity = self.equity_provider()
        if equity <= 0:
            return False
        if len(open_positions) >= self.limits.max_positions:
            return False
        current_weight = sum(open_positions.values())
        if current_weight >= self.limits.max_total_exposure_pct:
            return False
        if market in open_positions and open_positions[market] >= self.limits.max_position_pct:
            return False
        return True

    def position_size(self, entry_price: float, stop_price: float) -> float:
        equity = self.equity_provider()
        risk_amount = equity * self.limits.per_trade_risk_pct
        distance = abs(entry_price - stop_price)
        if distance == 0:
            return 0.0
        size = risk_amount / distance
        max_size = (equity * self.limits.max_position_pct) / entry_price
        return min(size, max_size)

    def register_pnl(self, realized: float) -> None:
        self.daily_loss += min(realized, 0.0)

    def hit_daily_limit(self, equity: float) -> bool:
        return abs(self.daily_loss) >= equity * self.limits.daily_loss_limit_pct
