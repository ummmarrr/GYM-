import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-key-that-is-long-enough-1234567890")
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("GROQ_API_KEY", "")
# The app's startup hook creates tables on whatever DATABASE_URL points at, and .env now
# points at Neon. Force a scratch file so a test run can never reach the real database.
# Set before importing app modules, because settings are read once at import time.
_scratch_db = Path(tempfile.gettempdir()) / "mastergym_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_scratch_db.as_posix()}"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db import Base, Role, User, get_db
from app.main import app


@pytest.fixture
def db_session() -> Iterator:
    """A fresh in-memory database per test, so tests cannot leak into each other."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session) -> Iterator[TestClient]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_plans(db_session):
    from app.db import MembershipPlan, default_plans

    db_session.add_all(default_plans())
    db_session.commit()
    return db_session.query(MembershipPlan).all()


def make_user(db_session, email: str, role: Role, password: str = "Password123") -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0].title(),
        password_hash=hash_password(password),
        role=role,
    )
    db_session.add(user)
    db_session.commit()
    return user


def auth_header(client: TestClient, email: str, password: str = "Password123") -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def admin(db_session):
    return make_user(db_session, "admin@example.com", Role.ADMIN)


@pytest.fixture
def trainer(db_session):
    return make_user(db_session, "trainer@example.com", Role.TRAINER)


@pytest.fixture
def member(db_session):
    return make_user(db_session, "member@example.com", Role.MEMBER)


