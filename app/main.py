"""Application entry point: builds the app, creates tables, wires the routers."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import config
from app.database import create_tables
from app.schemas import ErrorResponse, ValidationErrorItem
from app.routers import auth, conversations, health, quiz

DESCRIPTION = """
A learning-focused backend with accounts, private conversations and saved
message history.

**How to use the protected endpoints**

1. `POST /auth/register` with an email and password.
2. `POST /auth/login` with the same credentials to get a JWT.
3. Click **Authorize** at the top right and paste the token.
4. The `/conversations` endpoints are now available.

Conversations are private: every request is filtered by the account the token
belongs to, so one user can never see another user's threads.

The assistant replies come from **placeholder logic** — deterministic Python, no
model calls. Only `app/services.py` would change to connect a real model.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run once at startup: make sure the tables exist.

    A lifespan handler rather than the deprecated @app.on_event("startup").
    create_all only creates what is missing, so restarts are harmless and the
    data in app.db is left alone.
    """
    create_tables()
    yield


app = FastAPI(
    title=config.APP_NAME,
    version=config.APP_VERSION,
    description=DESCRIPTION,
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(conversations.router)
app.include_router(quiz.router)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, error: RequestValidationError):
    """Return validation failures as an object, matching every other response."""
    items = [
        ValidationErrorItem(
            field=".".join(str(part) for part in raw["loc"]),
            message=raw["msg"],
            type=raw["type"],
        )
        for raw in error.errors()
    ]

    fields = ", ".join(item.field for item in items) or "request body"

    body = ErrorResponse(
        error="validation_error",
        detail=f"The request was rejected. Check: {fields}.",
        errors=items,
    )

    # The literal 422: Starlette renamed HTTP_422_UNPROCESSABLE_ENTITY to
    # HTTP_422_UNPROCESSABLE_CONTENT, so either constant warns or breaks
    # depending on the installed version.
    return JSONResponse(status_code=422, content=body.model_dump(mode="json"))


@app.get("/", tags=["health"], summary="API index")
def read_root() -> dict:
    return {
        "name": config.APP_NAME,
        "version": config.APP_VERSION,
        "docs": "/docs",
        "public_endpoints": ["/", "/health", "/auth/register", "/auth/login"],
        "protected_endpoints": [
            "/auth/me",
            "/conversations",
            "/conversations/{id}",
            "/conversations/{id}/messages",
            "/quiz",
        ],
    }
