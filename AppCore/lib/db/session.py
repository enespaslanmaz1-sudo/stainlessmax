import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_DATABASE_ENV_VAR = "DATABASE_URL"


def get_database_url(env_var: str = DEFAULT_DATABASE_ENV_VAR) -> str:
    database_url = os.getenv(env_var, "").strip()
    if not database_url:
        raise RuntimeError(f"{env_var} is not set")
    return database_url


def create_engine_from_env(
    *,
    env_var: str = DEFAULT_DATABASE_ENV_VAR,
    echo: bool = False,
    pool_pre_ping: bool = True,
) -> Engine:
    return create_engine(
        get_database_url(env_var),
        echo=echo,
        future=True,
        pool_pre_ping=pool_pre_ping,
    )


def create_session_factory(
    engine: Engine | None = None,
    *,
    env_var: str = DEFAULT_DATABASE_ENV_VAR,
    expire_on_commit: bool = False,
) -> sessionmaker[Session]:
    if engine is None:
        engine = create_engine_from_env(env_var=env_var)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, expire_on_commit=expire_on_commit, future=True)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
