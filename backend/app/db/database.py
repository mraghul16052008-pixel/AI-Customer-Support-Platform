from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine

from app.core.config import settings


def create_database_url() -> URL:
    return URL.create(
        drivername="postgresql+psycopg",
        username=settings.db_user,
        password=settings.db_password.get_secret_value(),
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
    )


engine: Engine = create_engine(create_database_url(), pool_pre_ping=True)
