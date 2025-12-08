"""Upbit REST/WebSocket 어댑터.

- JWT 서명 포함 요청 헤더 생성
- 공통 예외 처리 및 재시도 정책은 상위 레이어에서 주입할 수 있도록 얇은 래퍼로 구성
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any, Iterable

import httpx
from pydantic import BaseModel

from upbit_bot.config import get_settings


class UpbitApiError(RuntimeError):
    """업비트 API 호출 오류를 표현."""


class OrderSide(str):
    BUY = "bid"
    SELL = "ask"


class Ticker(BaseModel):
    market: str
    trade_price: float
    signed_change_rate: float
    acc_trade_price_24h: float
    acc_trade_volume_24h: float | None = None


class Candle(BaseModel):
    market: str
    candle_date_time_utc: str
    opening_price: float
    high_price: float
    low_price: float
    trade_price: float
    timestamp: int
    candle_acc_trade_price: float | None = None
    candle_acc_trade_volume: float | None = None


def _sign_payload(query: dict[str, Any], secret_key: str, access_key: str) -> str:
    payload = json.dumps(query, separators=(',', ':'), ensure_ascii=False)
    query_hash = hashlib.sha512(payload.encode()).hexdigest()
    jwt_payload = {
        "access_key": access_key,
        "nonce": str(uuid.uuid4()),
        "query_hash": query_hash,
        "query_hash_alg": "SHA512",
    }
    header = base64.urlsafe_b64encode(b'{"typ":"JWT","alg":"HS256"}').decode().rstrip('=')
    body = base64.urlsafe_b64encode(json.dumps(jwt_payload).encode()).decode().rstrip('=')
    signature = hmac.new(secret_key.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(signature).decode().rstrip('=')
    return f"Bearer {header}.{body}.{sig}"


def _auth_headers(query: dict[str, Any]) -> dict[str, str]:
    settings = get_settings()
    token = _sign_payload(query, settings.upbit_secret_key, settings.upbit_access_key)
    return {"Authorization": token}


class UpbitClient:
    """업비트 REST 클라이언트.

    httpx.AsyncClient를 내부적으로 사용하며 타임아웃 및 커넥션 풀을 재사용한다.
    """

    def __init__(self, client: httpx.AsyncClient | None = None):
        settings = get_settings()
        self._client = client or httpx.AsyncClient(base_url=settings.rest_base_url, timeout=settings.request_timeout)

    async def list_markets(self, is_details: bool = False) -> list[dict[str, Any]]:
        res = await self._client.get("/v1/market/all", params={"isDetails": str(is_details).lower()})
        _ensure_ok(res)
        return res.json()

    async def tickers(self, markets: Iterable[str]) -> list[Ticker]:
        params = {"markets": ",".join(markets)}
        res = await self._client.get("/v1/ticker", params=params)
        _ensure_ok(res)
        return [Ticker(**item) for item in res.json()]

    async def minute_candles(self, market: str, unit: int = 1, count: int = 200) -> list[Candle]:
        endpoint = f"/v1/candles/minutes/{unit}"
        res = await self._client.get(endpoint, params={"market": market, "count": count})
        _ensure_ok(res)
        return [Candle(**item) for item in res.json()]

    async def day_candles(self, market: str, count: int = 60) -> list[Candle]:
        res = await self._client.get("/v1/candles/days", params={"market": market, "count": count})
        _ensure_ok(res)
        return [Candle(**item) for item in res.json()]

    async def order_chance(self, market: str) -> dict[str, Any]:
        query = {"market": market}
        headers = _auth_headers(query)
        res = await self._client.get("/v1/orders/chance", params=query, headers=headers)
        _ensure_ok(res)
        return res.json()

    async def place_order(
        self,
        market: str,
        side: OrderSide,
        volume: float | None,
        price: float | None,
        ord_type: str = "limit",
    ) -> dict[str, Any]:
        query = {
            "market": market,
            "side": side,
            "volume": str(volume) if volume is not None else None,
            "price": str(price) if price is not None else None,
            "ord_type": ord_type,
        }
        headers = _auth_headers({k: v for k, v in query.items() if v is not None})
        res = await self._client.post("/v1/orders", json=query, headers=headers)
        _ensure_ok(res)
        return res.json()

    async def balances(self) -> list[dict[str, Any]]:
        headers = _auth_headers({})
        res = await self._client.get("/v1/accounts", headers=headers)
        _ensure_ok(res)
        return res.json()

    async def close(self) -> None:
        await self._client.aclose()


class UpbitWebSocket:
    """실시간 시세·주문 데이터를 수신하기 위한 WebSocket 관리자."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        settings = get_settings()
        self.url = settings.websocket_url
        self.client = client or httpx.AsyncClient()

    async def subscribe(self, tickets: list[dict[str, Any]]):
        """주어진 티켓 목록을 기준으로 구독 스트림을 연다."""

        async with self.client.stream("GET", self.url, timeout=None) as response:
            if response.status_code != 101:
                raise UpbitApiError(f"WebSocket upgrade 실패: {response.status_code}")
            async for chunk in response.aiter_raw():
                yield chunk


def _ensure_ok(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        payload = response.json()
    except Exception:
        payload = response.text
    raise UpbitApiError(f"{response.status_code}: {payload}")
