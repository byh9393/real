"""대시보드용 FastAPI 엔드포인트."""
from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException

from upbit_bot.adapters.upbit import UpbitClient
from upbit_bot.config import get_settings

app = FastAPI(title="Upbit Trading Bot")


def get_client():
    return UpbitClient()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/markets")
async def markets(client: UpbitClient = Depends(get_client)):
    return await client.list_markets()


@app.get("/balances")
async def balances(client: UpbitClient = Depends(get_client)):
    try:
        return await client.balances()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
