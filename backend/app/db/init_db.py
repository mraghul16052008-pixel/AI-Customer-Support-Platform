from app.core.config import settings
from app.db.base import Base
from app.db.database import engine
import app.models  # noqa: F401


def init_db() -> None:
    if not settings.db_password.get_secret_value():
        raise RuntimeError(
            "DB_PASSWORD is not set. Add it to your local .env before initializing."
        )

    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database tables initialized successfully.")

