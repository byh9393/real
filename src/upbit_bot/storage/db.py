"""SQLAlchemy 기반 DB 스키마 정의."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from upbit_bot.config import get_settings

Base = declarative_base()


class AccountSnapshot(Base):
    __tablename__ = "accounts_snapshot"

    id = Column(Integer, primary_key=True)
    captured_at = Column(DateTime, default=datetime.utcnow, index=True)
    total_balance = Column(Float)
    equity = Column(Float)
    cash = Column(Float)


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True)
    market = Column(String, index=True)
    avg_price = Column(Float)
    volume = Column(Float)
    opened_at = Column(DateTime, default=datetime.utcnow)
    take_profit = Column(Float)
    stop_loss = Column(Float)
    trailing = Column(Float)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    uuid = Column(String, unique=True, index=True)
    market = Column(String, index=True)
    side = Column(String)
    price = Column(Float)
    volume = Column(Float)
    state = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    price = Column(Float)
    volume = Column(Float)
    fee = Column(Float)
    executed_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", backref="trades")


def get_engine():
    settings = get_settings()
    return create_engine(settings.database_url, future=True)


def create_session():
    engine = get_engine()
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)
