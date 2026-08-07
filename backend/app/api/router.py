from fastapi import APIRouter

from app.api.routes import admin, chat, company, health, orders


api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(company.router, tags=["Company"])
api_router.include_router(orders.router, tags=["Orders"])
api_router.include_router(chat.router, tags=["Chat"])
api_router.include_router(admin.router, tags=["Admin"])
