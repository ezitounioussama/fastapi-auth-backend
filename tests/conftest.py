"""Test fixtures: a throwaway database and helpers for registered users.

Each test gets a fresh in-memory SQLite database, so tests cannot see each
other's rows and none of them touch the real app.db.
"""

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.cache import quiz_cache
from app.database import Base, get_db
from app.main import app

BASE_URL = "http://testserver"


@pytest.fixture
def db_session():
    """A fresh in-memory database for one test.

    StaticPool with a shared in-memory URL matters here: by default each
    connection to ":memory:" gets its OWN empty database, so the tables created
    on one connection would be invisible to the next. StaticPool reuses a single
    connection, which keeps one database for the whole test.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    """An httpx client wired to the app, with the database swapped for the test one.

    dependency_overrides replaces get_db for the duration of the test, so the
    routes read and write the in-memory database instead of the real file.
    """

    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # the fixture owns the session's lifetime

    app.dependency_overrides[get_db] = override_get_db
    quiz_cache.clear()  # so cache tests do not inherit entries from another test

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as async_client:
        yield async_client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def register_and_login(client, email: str, password: str = "test-password-123") -> dict:
    """Create an account, log in, and return everything the tests need.

    Returns {"email", "password", "user_id", "token", "headers"}.
    """
    register = await client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert register.status_code == 201, register.text

    login = await client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text

    token = login.json()["access_token"]

    return {
        "email": email,
        "password": password,
        "user_id": register.json()["id"],
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest_asyncio.fixture
async def alice(client):
    """User A."""
    return await register_and_login(client, "alice@example.com")


@pytest_asyncio.fixture
async def bob(client):
    """User B — used to prove they cannot reach User A's data."""
    return await register_and_login(client, "bob@example.com")
