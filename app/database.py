"""Database connection and session handling.

SQLite is used because it needs no server: the whole database is one file
(app.db) next to the code, which suits a learning project.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app import config

# check_same_thread=False is required for SQLite with FastAPI. SQLite normally
# refuses to use a connection from a different thread than the one that created
# it, and FastAPI serves requests from a thread pool. SQLAlchemy's pool keeps
# each connection to one request at a time, so lifting the check is safe here.
connect_args = {}
if config.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(config.DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Parent class for every table model."""


def get_db():
    """FastAPI dependency that hands a session to a route and always closes it.

    The try/finally matters: without it a failing request would leak its
    connection and the pool would eventually run dry.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create any missing tables. Safe to call repeatedly."""
    Base.metadata.create_all(bind=engine)
