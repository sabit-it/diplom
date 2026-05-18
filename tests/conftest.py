import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from main import app

engine = create_engine(settings.DATABASE_URL)


@pytest.fixture()
def db():
    # откатываем всё после каждого теста, чтобы не засорять базу
    with engine.connect() as conn:
        tx = conn.begin()
        session = Session(conn, join_transaction_mode="create_savepoint")
        yield session
        session.close()
        tx.rollback()


@pytest.fixture()
def client(db: Session):
    def override():
        yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
