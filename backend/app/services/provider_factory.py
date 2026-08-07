from app.core.config import settings
from app.services.gemini_provider import GeminiProvider
from app.services.support_ai import SupportAIService


def create_support_ai_service(
    *, api_key: str | None = None, model: str | None = None
) -> SupportAIService:
    configured_key = (
        settings.gemini_api_key.get_secret_value() if api_key is None else api_key
    )
    configured_model = settings.gemini_model if model is None else model
    if not configured_key:
        return SupportAIService()

    try:
        provider = GeminiProvider(api_key=configured_key, model=configured_model)
    except Exception:
        return SupportAIService()
    return SupportAIService(provider=provider)


support_ai_service = create_support_ai_service()
