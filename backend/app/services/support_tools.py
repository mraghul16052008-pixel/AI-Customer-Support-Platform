from typing import Protocol

from app.services.support_types import SupportContext, SupportIntent, TrustedEvidence


class TrustedSupportTools(Protocol):
    def get_order_evidence(self, context: SupportContext) -> TrustedEvidence: ...

    def get_packing_evidence(self, context: SupportContext) -> TrustedEvidence: ...

    def get_tracking_evidence(self, context: SupportContext) -> TrustedEvidence: ...

    def get_payment_metadata(self, context: SupportContext) -> TrustedEvidence: ...


class ContextSupportTools:
    """Small replaceable boundary around facts the backend actually has."""

    def get_order_evidence(self, context: SupportContext) -> TrustedEvidence:
        if not any(
            (context.external_order_id, context.product_name, context.order_status)
        ):
            return TrustedEvidence(
                source="order_record",
                available=False,
                summary="No order is attached to this conversation.",
            )
        parts = []
        if context.external_order_id:
            parts.append(f"order {context.external_order_id}")
        if context.product_name:
            parts.append(f"product {context.product_name}")
        if context.order_status:
            parts.append(f"status {context.order_status}")
        return TrustedEvidence(
            source="order_record",
            available=True,
            summary="; ".join(parts),
        )

    def get_packing_evidence(self, context: SupportContext) -> TrustedEvidence:
        return TrustedEvidence(
            source="packing_evidence",
            available=False,
            summary="No trusted ShopX packing evidence source is configured.",
        )

    def get_tracking_evidence(self, context: SupportContext) -> TrustedEvidence:
        return TrustedEvidence(
            source="tracking_evidence",
            available=False,
            summary="No trusted courier tracking evidence source is configured.",
        )

    def get_payment_metadata(self, context: SupportContext) -> TrustedEvidence:
        return TrustedEvidence(
            source="payment_metadata",
            available=False,
            summary="No safe payment metadata source is configured.",
        )

    def evidence_for(
        self, intent: SupportIntent, context: SupportContext
    ) -> tuple[TrustedEvidence, ...]:
        evidence = [self.get_order_evidence(context)]
        if intent in (SupportIntent.DELIVERY_ISSUE, SupportIntent.REFUND):
            evidence.extend(
                (
                    self.get_packing_evidence(context),
                    self.get_tracking_evidence(context),
                )
            )
        if intent == SupportIntent.PAYMENT_ISSUE:
            evidence.append(self.get_payment_metadata(context))
        return tuple(evidence)
