"""Registration, login, and "who am I".

The auth flow, end to end:

    POST /auth/register  email + password  ->  password is hashed, user row saved
    POST /auth/login     email + password  ->  hash compared, JWT returned
    GET  /auth/me        Bearer token      ->  token decoded, user row returned

The password itself is never stored and never returned at any point.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.dependencies import get_current_user
from app.models_db import User
from app.schemas import (
    ErrorResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"model": ErrorResponse, "description": "Email already registered"},
        422: {"model": ErrorResponse, "description": "Validation failed"},
    },
    summary="Create an account",
    description=(
        "Registers a new user. The password is hashed with bcrypt before it is "
        "stored — the raw value is never written to the database and never "
        "appears in a response."
    ),
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    # Check first so the normal case gets a clean 409 rather than a database error.
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That email is already registered.",
        )

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )

    db.add(user)

    try:
        db.commit()
    except IntegrityError:
        # The unique constraint on users.email is the real guard. Two requests
        # arriving at the same moment can both pass the check above, and only
        # the database can settle it — so the same 409 is raised here too.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That email is already registered.",
        )

    db.refresh(user)

    # Returning the ORM object is safe: UserResponse has no password field, so
    # FastAPI drops hashed_password on the way out.
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={401: {"model": ErrorResponse, "description": "Bad credentials"}},
    summary="Log in and get a token",
    description=(
        "Checks the email and password and returns a JWT access token. Send it "
        "on later requests as `Authorization: Bearer <token>`."
    ),
)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == payload.email).first()

    # One message for both "no such email" and "wrong password". Telling them
    # apart would let someone enumerate which addresses have accounts.
    #
    # verify_password is still called when the user is missing, against a dummy
    # hash, so both paths take a similar amount of time. Returning instantly for
    # an unknown email is itself a signal an attacker can measure.
    if user is None:
        verify_password(payload.password, hash_password("dummy-password-for-timing"))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    token = create_access_token(user_id=user.id, email=user.email)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES,
        user=UserResponse.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    responses={401: {"model": ErrorResponse, "description": "Not authenticated"}},
    summary="Who am I",
    description="Returns the account belonging to the token that was sent.",
)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
