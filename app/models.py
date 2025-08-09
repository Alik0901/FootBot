# app/models.py
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///subscriptions.db")

# Railway Postgres обычно требует sslmode=require
connect_args = {"sslmode": "require"} if DATABASE_URL.startswith(("postgres://", "postgresql://")) else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class Subscription(Base):
    __tablename__ = "subscriptions"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(BigInteger, index=True, nullable=False)  # TG ID может быть > int32
    plan       = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # UTC naive


def init_db():
    Base.metadata.create_all(bind=engine)
