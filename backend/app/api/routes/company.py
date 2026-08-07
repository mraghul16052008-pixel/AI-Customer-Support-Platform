from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_company
from app.models import Company


router = APIRouter()


@router.get("/company/me")
def get_company_me(
    current_company: Annotated[Company, Depends(get_current_company)],
) -> dict[str, int | str]:
    return {"id": current_company.id, "name": current_company.name}
