# 시스템 아키텍처 요약

본 레포지토리는 README.MD에 정의된 요구사항을 바탕으로 업비트 자동매매 시스템의 핵심 골격을 제공합니다.

- **config**: 환경 변수 기반 설정(`upbit_bot.config`).
- **adapters**: 업비트 REST/WebSocket 호출 래퍼(`UpbitClient`). JWT 서명 지원.
- **data**: 거래 유니버스 조회 및 OHLCV 캐시(`MarketUniverse`, `CandleCache`).
- **strategy**: EMA 및 모멘텀 기반 스코어링과 신호 생성(`StrategyEngine`).
- **risk**: 포지션 사이징 및 손실 한도 계산(`RiskEngine`).
- **execution**: 리스크 반영 주문 사이즈 산출과 제한가 주문 전송(`ExecutionEngine`).
- **storage**: SQLAlchemy 기반 계좌/포지션/주문/체결 테이블과 초기화 헬퍼(`init_db`).
- **server**: FastAPI 대시보드용 기본 엔드포인트(`/health`, `/markets`, `/balances`).

실거래 연동과 리스크 관리, 전략 확장에 필요한 구조적 포인트를 모두 노출해 확장 가능성을 확보했습니다.
