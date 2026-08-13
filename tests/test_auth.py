"""Registration, login and token handling."""

import jwt

from app import config
from app.models_db import User


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------


async def test_register_creates_an_account(client):
    response = await client.post(
        "/auth/register", json={"email": "new@example.com", "password": "a-good-password"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["id"] > 0


async def test_register_never_returns_a_password(client):
    """No password field of any kind may appear in the response."""
    response = await client.post(
        "/auth/register", json={"email": "quiet@example.com", "password": "a-good-password"}
    )

    body = response.json()
    assert "password" not in body
    assert "hashed_password" not in body
    assert "a-good-password" not in response.text


async def test_the_raw_password_is_not_in_the_database(client, db_session):
    """The stored value must be a bcrypt hash, not the password."""
    password = "plaintext-must-not-persist"
    await client.post(
        "/auth/register", json={"email": "hash@example.com", "password": password}
    )

    user = db_session.query(User).filter(User.email == "hash@example.com").first()

    assert user is not None
    assert user.hashed_password != password
    assert password not in user.hashed_password
    # bcrypt hashes start with $2b$ and are 60 characters long.
    assert user.hashed_password.startswith("$2b$")
    assert len(user.hashed_password) == 60


async def test_two_users_with_the_same_password_get_different_hashes(client, db_session):
    """Proves the hashes are salted: identical passwords must not collide."""
    for email in ("same1@example.com", "same2@example.com"):
        await client.post("/auth/register", json={"email": email, "password": "identical-pw"})

    hashes = [
        user.hashed_password
        for user in db_session.query(User).filter(User.email.like("same%")).all()
    ]

    assert len(hashes) == 2
    assert hashes[0] != hashes[1]


async def test_duplicate_email_is_rejected(client):
    payload = {"email": "taken@example.com", "password": "a-good-password"}

    first = await client.post("/auth/register", json=payload)
    second = await client.post("/auth/register", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


async def test_register_rejects_a_bad_email(client):
    response = await client.post(
        "/auth/register", json={"email": "not-an-email", "password": "a-good-password"}
    )
    assert response.status_code == 422


async def test_register_rejects_a_short_password(client):
    response = await client.post(
        "/auth/register", json={"email": "short@example.com", "password": "abc"}
    )
    assert response.status_code == 422

    fields = [item["field"] for item in response.json()["errors"]]
    assert "body.password" in fields


# --------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------


async def test_login_returns_a_token(client, alice):
    response = await client.post(
        "/auth/login", json={"email": alice["email"], "password": alice["password"]}
    )

    body = response.json()
    assert response.status_code == 200
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == alice["email"]


async def test_the_token_is_a_valid_jwt_naming_the_user(client, alice):
    payload = jwt.decode(
        alice["token"], config.SECRET_KEY, algorithms=[config.ALGORITHM]
    )

    assert payload["sub"] == str(alice["user_id"])
    assert payload["email"] == alice["email"]
    assert "exp" in payload


async def test_login_with_the_wrong_password_is_rejected(client, alice):
    response = await client.post(
        "/auth/login", json={"email": alice["email"], "password": "wrong-password"}
    )
    assert response.status_code == 401


async def test_login_with_an_unknown_email_is_rejected(client):
    response = await client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "any-password"}
    )
    assert response.status_code == 401


async def test_both_login_failures_give_the_same_message(client, alice):
    """Different messages would reveal which emails have accounts."""
    wrong_password = await client.post(
        "/auth/login", json={"email": alice["email"], "password": "wrong"}
    )
    no_such_user = await client.post(
        "/auth/login", json={"email": "ghost@example.com", "password": "wrong"}
    )

    assert wrong_password.json() == no_such_user.json()


# --------------------------------------------------------------------------
# Using the token
# --------------------------------------------------------------------------


async def test_me_returns_the_current_user(client, alice):
    response = await client.get("/auth/me", headers=alice["headers"])

    assert response.status_code == 200
    assert response.json()["email"] == alice["email"]


async def test_me_without_a_token_is_401(client):
    response = await client.get("/auth/me")
    assert response.status_code == 401


async def test_a_tampered_token_is_rejected(client, alice):
    """Flipping a character breaks the signature, which must be checked."""
    broken = alice["token"][:-4] + "AAAA"

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {broken}"})
    assert response.status_code == 401


async def test_a_token_signed_with_another_key_is_rejected(client, alice):
    """Someone forging a token needs the SECRET_KEY; a different key must fail."""
    # A full-length key, so PyJWT does not warn about a short HMAC secret —
    # the point of the test is the WRONG key, not a weak one.
    forged = jwt.encode(
        {"sub": str(alice["user_id"]), "email": alice["email"]},
        "an-attackers-own-secret-key-of-adequate-length",
        algorithm=config.ALGORITHM,
    )

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


async def test_an_expired_token_is_rejected(client, alice):
    from datetime import datetime, timedelta, timezone

    past = datetime.now(timezone.utc) - timedelta(hours=2)
    expired = jwt.encode(
        {"sub": str(alice["user_id"]), "email": alice["email"], "exp": past},
        config.SECRET_KEY,
        algorithm=config.ALGORITHM,
    )

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


async def test_a_token_for_a_deleted_user_is_rejected(client, alice, db_session):
    """A signed token can still point at an account that no longer exists."""
    user = db_session.query(User).filter(User.email == alice["email"]).first()
    db_session.delete(user)
    db_session.commit()

    response = await client.get("/auth/me", headers=alice["headers"])
    assert response.status_code == 401


async def test_a_malformed_authorization_header_is_rejected(client):
    for header in ({"Authorization": "Bearer"}, {"Authorization": "not-a-scheme abc"},
                   {"Authorization": "Bearer not.a.jwt"}):
        response = await client.get("/auth/me", headers=header)
        assert response.status_code == 401, header
