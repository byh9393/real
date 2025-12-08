"""완전 자동매매 실행 루프.

- 유니버스 선정 → 신호 계산 → 리스크/주문 계산 → 체결 요청까지 자동 처리
- 업비트 실계좌/모의계좌 모두 동일한 플로우를 사용할 수 있도록 설계
"""
from __future__ import annotations

import asyncio
import logging
from typing import Iterable

from upbit_bot.adapters.upbit import Ticker, UpbitClient
from upbit_bot.data.market_data import MarketDataService, MarketUniverse, UniverseFilter
from upbit_bot.execution.engine import ExecutionEngine
from upbit_bot.risk.engine import RiskEngine
from upbit_bot.strategy.engine import PositionSnapshot, Signal, StrategyEngine

logger = logging.getLogger(__name__)


class PortfolioState:
    """계좌 상태와 포지션 메타데이터를 캐싱한다."""

    def __init__(self):
        self.equity: float = 0.0
        self.cash: float = 0.0
        self.positions: dict[str, PositionSnapshot] = {}

    def open_weights(self) -> dict[str, float]:
        if self.equity == 0:
            return {}
        weights: dict[str, float] = {}
        for market, pos in self.positions.items():
            weights[market] = (pos.entry_price * pos.volume) / self.equity
        return weights


class AutoTradingBot:
    """지표 기반 자동매매의 메인 오케스트레이터."""

    def __init__(self, client: UpbitClient | None = None):
        self.client = client or UpbitClient()
        self.universe = MarketUniverse(self.client)
        self.universe_filter = UniverseFilter(self.client)
        self.data = MarketDataService(self.client)
        self.state = PortfolioState()
        self.strategy = StrategyEngine()
        self.risk_engine = RiskEngine(lambda: self.state.equity)
        self.execution = ExecutionEngine(self.client, self.risk_engine)

    async def _fetch_tickers(self, markets: Iterable[str]) -> dict[str, Ticker]:
        tickers = await self.client.tickers(markets)
        return {t.market: t for t in tickers}

    async def refresh_portfolio(self) -> None:
        """업비트 계좌 정보를 바탕으로 현금/포지션/총액을 동기화한다."""

        balances = await self.client.balances()
        krw = 0.0
        holding_markets: dict[str, float] = {}
        avg_price: dict[str, float] = {}

        for bal in balances:
            currency = bal.get("currency")
            total_qty = float(bal.get("balance", 0)) + float(bal.get("locked", 0))
            if currency == "KRW":
                krw += total_qty
            else:
                market = f"KRW-{currency}"
                holding_markets[market] = total_qty
                avg_price[market] = float(bal.get("avg_buy_price", 0))

        tickers = await self._fetch_tickers(holding_markets.keys()) if holding_markets else {}
        equity = krw
        positions: dict[str, PositionSnapshot] = {}

        for market, qty in holding_markets.items():
            price = tickers.get(market).trade_price if market in tickers else avg_price.get(market, 0)
            equity += price * qty
            positions[market] = PositionSnapshot(
                market=market,
                side="buy",
                entry_price=avg_price.get(market, price),
                volume=qty,
                stop=price * 0.97,
                take_profit=price * 1.05,
                trailing=price * 0.02,
            )

        self.state.equity = equity
        self.state.cash = krw
        self.state.positions = positions

    async def _select_universe(self) -> list[str]:
        markets = await self.universe.fetch_krw_markets()
        return await self.universe_filter.filter_by_liquidity(markets, top_n=50)

    async def _generate_signals(self, markets: list[str]) -> dict[str, Signal]:
        candles = await self.data.fetch_multi(markets, unit=5, count=200)
        signals: dict[str, Signal] = {}
        for market, frame in candles.items():
            sig = self.strategy.generate_entry_signal(market, frame)
            if sig:
                signals[market] = sig
        return signals

    async def _exit_checks(self, markets: Iterable[str]) -> None:
        if not self.state.positions:
            return

        candles = await self.data.fetch_multi(markets, unit=5, count=200)
        for market, pos in list(self.state.positions.items()):
            frame = candles.get(market)
            if frame is None or frame.empty:
                continue
            if self.strategy.should_exit(frame, pos):
                price = self.execution.align_price(frame["close"].iloc[-1])
                await self.execution.submit_limit_order(market, "sell" if pos.side == "buy" else "buy", price, pos.volume)
                logger.info("%s 포지션 종료: %.4f", market, price)
                self.state.positions.pop(market, None)

    async def _enter_positions(self, signals: dict[str, Signal]) -> None:
        if self.risk_engine.hit_daily_limit(self.state.equity):
            logger.warning("일일 손실 한도 도달로 신규 진입 차단")
            return

        open_weights = self.state.open_weights()
        ordered = sorted(signals.values(), key=lambda s: abs(s.score), reverse=True)
        for signal in ordered:
            if not self.risk_engine.can_open_new_position(signal.market, open_weights):
                continue
            price, volume = await self.execution.build_order(
                signal.market,
                signal.side,
                signal.entry,
                signal.stop,
                cash_available=self.state.cash,
            )
            if volume <= 0:
                continue
            await self.execution.submit_limit_order(signal.market, signal.side, price, volume)
            weight = (price * volume) / self.state.equity if self.state.equity else 0
            open_weights[signal.market] = open_weights.get(signal.market, 0) + weight
            self.state.cash -= price * volume
            self.state.positions[signal.market] = PositionSnapshot(
                market=signal.market,
                side=signal.side,
                entry_price=price,
                volume=volume,
                stop=signal.stop,
                take_profit=signal.take_profit,
                trailing=signal.trailing,
            )
            logger.info("신규 진입 %s %s @ %.4f 수량 %.6f", signal.market, signal.side, price, volume)

    async def run_cycle(self) -> None:
        """단일 사이클: 계좌 갱신 → 유니버스/신호 → 청산 → 신규 진입."""

        await self.refresh_portfolio()
        universe = await self._select_universe()
        signals = await self._generate_signals(universe)

        await self._exit_checks(self.state.positions.keys())
        await self._enter_positions(signals)

    async def run_forever(self, interval_sec: int = 60) -> None:
        while True:
            try:
                await self.run_cycle()
            except Exception as exc:  # noqa: BLE001
                logger.exception("자동매매 사이클 오류: %s", exc)
            await asyncio.sleep(interval_sec)
