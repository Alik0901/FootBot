import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Получаем URL базы из переменных окружения, по умолчанию SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///subscriptions.db")

# Настройка движка SQLAlchemy
# Если это Postgres, включаем sslmode=require
connect_args = {"sslmode": "require"} if DATABASE_URL.startswith("postgres") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

# Фабрика сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс для моделей
Base = declarative_base()

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True, nullable=False)
    plan = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)


def init_db():
    """
    Создает все таблицы в базе данных.
    Вызывать при старте приложения:
    from app.models import init_db
    init_db()
    """
    Base.metadata.create_all(bind=engine)
