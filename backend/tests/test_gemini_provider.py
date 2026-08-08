import json
import unittest
from unittest.mock import patch

from app.schemas.chat import ChatResponse
from app.services.gemini_provider import GeminiProvider
from app.services.provider_factory import create_support_ai_service
from app.services.support_ai import (
    SupportAIService,
    SupportContext,
    SupportIntent,
    SupportTurn,
)


class FakeResponse:
    def __init__(self, text: str | None) -> None:
        self.text = text


class FakeModels:
    def __init__(self, *, text: str | None = None, error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs: object) -> FakeResponse:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return FakeResponse(self.text)


class FakeClient:
    def __init__(self, *, text: str | None = None, error: Exception | None = None) -> None:
        self.models = FakeModels(text=text, error=error)


class GeminiProviderTests(unittest.TestCase):
    @staticmethod
    def _schema_keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {
                key
                for child in value.values()
                for key in GeminiProviderTests._schema_keys(child)
            }
        if isinstance(value, list):
            return {
                key
                for child in value
                for key in GeminiProviderTests._schema_keys(child)
            }
        return set()

    @staticmethod
    def _json_response(
        *,
        reply: str = "I can help with that.",
        intent: str = "general_query",
        confidence: float = 0.85,
        should_escalate: bool = False,
        escalation_reason: str | None = None,
    ) -> str:
        return json.dumps(
            {
                "reply": reply,
                "intent": intent,
                "confidence": confidence,
                "should_escalate": should_escalate,
                "escalation_reason": escalation_reason,
            }
        )

    def _provider(
        self, *, text: str | None = None, error: Exception | None = None
    ) -> tuple[GeminiProvider, FakeClient]:
        client = FakeClient(text=text, error=error)
        return (
            GeminiProvider(
                api_key="unit-test-secret-key",
                model="gemini-test-model",
                client=client,
            ),
            client,
        )

    def test_gemini_valid_response(self) -> None:
        provider, client = self._provider(text=self._json_response())
        result = provider.respond(SupportContext(message="Can you help me?"))
        self.assertEqual(result.reply, "I can help with that.")
        self.assertEqual(client.models.calls[0]["model"], "gemini-test-model")

    def test_gemini_response_schema_omits_unsupported_additional_properties(
        self,
    ) -> None:
        provider, client = self._provider(text=self._json_response())
        provider.respond(SupportContext(message="Can you help me?"))

        config = client.models.calls[0]["config"]
        schema = config.response_schema  # type: ignore[union-attr]
        schema_keys = self._schema_keys(schema)

        self.assertNotIn("additionalProperties", schema_keys)
        self.assertNotIn("additional_properties", schema_keys)

    def test_provider_observation_records_success_without_secrets(self) -> None:
        secret = "observation-secret-key"
        client = FakeClient(text=self._json_response())
        service = SupportAIService(
            provider=GeminiProvider(
                api_key=secret,
                model="gemini-test-model",
                client=client,
            )
        )
        service.respond(SupportContext(message="Can you help me?"))
        observation = service.last_observation
        self.assertEqual(observation.selected_provider, "GeminiProvider")
        self.assertTrue(observation.request_attempted)
        self.assertTrue(observation.provider_succeeded)
        self.assertFalse(observation.fallback_used)
        self.assertNotIn(secret, repr(observation))

    def test_gemini_intent_parsing(self) -> None:
        provider, _ = self._provider(
            text=self._json_response(intent="delivery_issue")
        )
        result = provider.respond(SupportContext(message="My delivery is late"))
        self.assertEqual(result.intent, SupportIntent.DELIVERY_ISSUE)

    def test_gemini_confidence_parsing(self) -> None:
        provider, _ = self._provider(text=self._json_response(confidence=0.82))
        result = provider.respond(SupportContext(message="Can you help me?"))
        self.assertEqual(result.confidence, 0.82)

    def test_gemini_escalation_parsing(self) -> None:
        provider, _ = self._provider(
            text=self._json_response(
                intent="refund",
                should_escalate=True,
                escalation_reason="Refund review required.",
            )
        )
        result = provider.respond(SupportContext(message="I need a refund"))
        self.assertTrue(result.should_escalate)
        self.assertEqual(result.escalation_reason, "Refund review required.")

    def test_malformed_gemini_response_uses_fallback(self) -> None:
        provider, _ = self._provider(text="not valid json")
        service = SupportAIService(provider=provider)
        result = service.respond(
            SupportContext(message="Where is my order?", order_status="processing")
        )
        self.assertEqual(result.intent, SupportIntent.ORDER_STATUS)
        self.assertEqual(result.confidence, 0.91)

    def test_empty_gemini_response_uses_fallback(self) -> None:
        provider, _ = self._provider(text="")
        service = SupportAIService(provider=provider)
        result = service.respond(SupportContext(message="Where is my order?"))
        self.assertEqual(result.intent, SupportIntent.ORDER_STATUS)

    def test_network_exception_uses_fallback(self) -> None:
        provider, _ = self._provider(error=TimeoutError("network timeout"))
        service = SupportAIService(provider=provider)
        result = service.respond(SupportContext(message="My delivery is late"))
        self.assertEqual(result.intent, SupportIntent.DELIVERY_ISSUE)
        self.assertTrue(service.last_observation.request_attempted)
        self.assertFalse(service.last_observation.provider_succeeded)
        self.assertTrue(service.last_observation.fallback_used)
        self.assertEqual(service.last_observation.error_type, "TimeoutError")

    def test_missing_api_key_selects_deterministic_fallback(self) -> None:
        service = create_support_ai_service(api_key="", model="gemini-test-model")
        self.assertIsNone(service.provider)
        result = service.respond(SupportContext(message="Where is my order?"))
        self.assertEqual(result.intent, SupportIntent.ORDER_STATUS)

    @patch("app.services.provider_factory.GeminiProvider")
    def test_configured_api_key_selects_gemini_provider(self, provider: object) -> None:
        service = create_support_ai_service(
            api_key="configured-test-key", model="configured-test-model"
        )
        provider.assert_called_once_with(  # type: ignore[attr-defined]
            api_key="configured-test-key", model="configured-test-model"
        )
        self.assertIs(service.provider, provider.return_value)  # type: ignore[attr-defined]

    def test_unsupported_intent_uses_fallback(self) -> None:
        provider, _ = self._provider(
            text=self._json_response(intent="unsupported_intent")
        )
        service = SupportAIService(provider=provider)
        result = service.respond(SupportContext(message="Where is my order?"))
        self.assertEqual(result.intent, SupportIntent.ORDER_STATUS)

    def test_confidence_below_threshold_is_forced_to_escalate(self) -> None:
        provider, _ = self._provider(
            text=self._json_response(confidence=0.40, should_escalate=False)
        )
        service = SupportAIService(provider=provider)
        result = service.respond(SupportContext(message="Please help"))
        self.assertTrue(result.should_escalate)
        self.assertIn("Low-confidence", result.escalation_reason)

    def test_sensitive_request_is_forced_to_escalate(self) -> None:
        provider, _ = self._provider(
            text=self._json_response(
                intent="general_query",
                confidence=0.95,
                should_escalate=False,
            )
        )
        service = SupportAIService(provider=provider)
        result = service.respond(SupportContext(message="I need a refund"))
        self.assertTrue(result.should_escalate)
        self.assertEqual(result.escalation_reason, "Refund requests require human review.")

    def test_sensitive_history_keeps_follow_up_under_human_review(self) -> None:
        provider, _ = self._provider(
            text=self._json_response(
                intent="delivery_issue",
                confidence=0.95,
                should_escalate=False,
            )
        )
        service = SupportAIService(provider=provider)
        result = service.respond(
            SupportContext(
                message="The outer box looked fine",
                history=(
                    SupportTurn(
                        sender_type="CUSTOMER",
                        content="My headphones arrived damaged",
                    ),
                ),
            )
        )
        self.assertTrue(result.should_escalate)
        self.assertEqual(
            result.escalation_reason,
            "A lost or damaged delivery requires human review.",
        )

    def test_backend_order_status_overrides_provider_claim(self) -> None:
        provider, _ = self._provider(
            text=self._json_response(
                reply="Your order was delivered.",
                intent="order_status",
                confidence=0.95,
            )
        )
        service = SupportAIService(provider=provider)
        result = service.respond(
            SupportContext(message="Where is my order?", order_status="processing")
        )
        self.assertIn("current status is processing", result.reply)
        self.assertIn("latest status available in ShopX", result.reply)
        self.assertNotIn("delivered", result.reply)

    def test_prompt_contains_backend_context_without_api_key(self) -> None:
        secret = "api-key-that-must-not-leak"
        client = FakeClient(text=self._json_response())
        provider = GeminiProvider(
            api_key=secret,
            model="gemini-test-model",
            client=client,
        )
        result = provider.respond(
            SupportContext(
                message="Where is my order?",
                customer_name="Demo Customer",
                external_order_id="SHOPX-1001",
                product_name="Headphones",
                order_status="processing",
            )
        )
        request_data = repr(client.models.calls)
        response_data = ChatResponse(
            conversation_id=1,
            reply=result.reply,
            intent=result.intent.value,
            confidence=result.confidence,
            should_escalate=result.should_escalate,
            escalation_id=None,
        ).model_dump_json()
        self.assertIn("Demo Customer", request_data)
        self.assertIn("Headphones", request_data)
        self.assertIn("processing", request_data)
        self.assertNotIn(secret, request_data)
        self.assertNotIn(secret, response_data)

    def test_prompt_contains_conversation_history_for_follow_up(self) -> None:
        provider, client = self._provider(
            text=self._json_response(
                reply="Thanks. Is the product itself cracked or not working?",
                intent="delivery_issue",
                confidence=0.90,
                should_escalate=True,
                escalation_reason="Damaged delivery requires human review.",
            )
        )
        provider.respond(
            SupportContext(
                message="The outer box looked fine",
                customer_name="Demo Customer",
                product_name="Headphones",
                history=(
                    SupportTurn(
                        sender_type="CUSTOMER",
                        content="My headphones arrived damaged",
                    ),
                    SupportTurn(
                        sender_type="AI",
                        content="Was the outer package damaged too?",
                    ),
                ),
            )
        )

        prompt = str(client.models.calls[0]["contents"])
        self.assertIn("conversation_history", prompt)
        self.assertIn("My headphones arrived damaged", prompt)
        self.assertIn("Was the outer package damaged too?", prompt)
        self.assertIn("The outer box looked fine", prompt)
        self.assertIn("trusted_backend_context", prompt)


if __name__ == "__main__":
    unittest.main()
