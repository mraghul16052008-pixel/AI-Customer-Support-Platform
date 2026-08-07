from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Company


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_current_company(
    api_key: Annotated[str | None, Security(api_key_header)],
    db: Annotated[Session, Depends(get_db)],
) -> Company:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
        )

    company = db.scalar(select(Company).where(Company.api_key == api_key))
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
        )

    return company

