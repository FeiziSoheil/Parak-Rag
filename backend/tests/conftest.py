import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import create_access_token, get_password_hash
from app.models import User, CartItem, Order, OrderItem  # noqa: F401
from app.api import auth
from app.api import cart as cart_api
from app.api import orders as orders_api


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app = FastAPI()
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(cart_api.router, prefix="/api", tags=["cart"])
    app.include_router(orders_api.router, prefix="/api", tags=["orders"])
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def user_a(db_session):
    u = User(username="alice", password_hash=get_password_hash("password123"), email_verified=True)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture()
def user_b(db_session):
    u = User(username="bob", password_hash=get_password_hash("password123"), email_verified=True)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture()
def auth_header_a(user_a):
    token = create_access_token({"sub": user_a.username})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def auth_header_b(user_b):
    token = create_access_token({"sub": user_b.username})
    return {"Authorization": f"Bearer {token}"}
