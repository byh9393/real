"""글로벌 설정 모듈.

실서비스 배포를 염두에 두고 환경 변수 기반 설정을 관리한다.
"""
from __future__ import annotations

from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """애플리케이션 공통 설정.

    - 환경 변수로 API Key, DB URL 등을 주입한다.
    - .env 파일을 사용해 로컬 개발 환경에서 값을 로드할 수 있다.
    """

    upbit_access_key: str = Field(..., description="업비트 Access Key")
    upbit_secret_key: str = Field(..., description="업비트 Secret Key")
    database_url: str = Field(..., description="SQLAlchemy 연결 문자열")
    redis_url: str | None = Field(None, description="선택적 Redis 캐시 URL")

    request_timeout: float = Field(10.0, description="REST 호출 타임아웃")
    rest_base_url: str = Field("https://api.upbit.com", description="업비트 REST 기본 URL")
    websocket_url: str = Field("wss://api.upbit.com/websocket/v1", description="업비트 WebSocket URL")

    backtest_data_dir: str = Field("data/cache", description="백테스트/히스토리 데이터 저장 경로")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings() -> Settings:
    """런타임에 단일 Settings 인스턴스를 제공한다."""

    return Settings()
