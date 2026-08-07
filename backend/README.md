# Customer Support AI Backend

Person 1's backend/API service for the hackathon project.

## Backend foundation

The first checkpoint provides:

- FastAPI application
- Versioned API prefix (`/api/v1`)
- CORS configuration for client applications
- Health-check endpoint
- PostgreSQL connectivity and shared SQLAlchemy models
- Company authentication through the `X-API-Key` header
- Automatic Swagger API documentation

## Run locally

Create and activate a virtual environment, then install the dependencies:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open these URLs:

- API: http://127.0.0.1:8000/
- Health: http://127.0.0.1:8000/api/v1/health
- Database health: http://127.0.0.1:8000/api/v1/health/db
- Swagger docs: http://127.0.0.1:8000/docs

Expected health response:

```json
{"status":"ok"}
```

## Database setup

Copy `.env.example` to `.env` and set `DB_PASSWORD` locally. Never commit `.env`.
Initialize the demo tables with:

```powershell
.\.venv\Scripts\python.exe -m app.db.init_db
```

The initializer uses SQLAlchemy `create_all`, so it is safe to run more than once for
this hackathon demo. It creates missing tables but does not replace migrations for a
production deployment.

Set a demo-only company API key in `.env`, then seed ShopX and its integration
customer:

```env
DEMO_COMPANY_API_KEY=your_demo_api_key
```

```powershell
.\.venv\Scripts\python.exe -m app.db.seed_demo
```

The seed is idempotent: it reuses ShopX and `demo@shopx.local` when they already
exist, and updates ShopX to the configured demo API key without printing it.

Test the authenticated company endpoint with:

```powershell
$headers = @{ "X-API-Key" = $env:DEMO_COMPANY_API_KEY }
Invoke-RestMethod -Headers $headers http://127.0.0.1:8000/api/v1/company/me
```

Business routes can identify the tenant by importing the authentication dependency:

```python
from typing import Annotated

from fastapi import Depends

from app.api.dependencies import get_current_company
from app.models import Company


CurrentCompany = Annotated[Company, Depends(get_current_company)]
```

Every query for tenant-owned data must filter with `company_id=current_company.id`.
Messages inherit tenant ownership through their conversation.

## Orders and support chat

The tenant-authenticated API exposes:

- `POST /api/v1/orders`
- `GET /api/v1/orders/{order_id}`
- `GET /api/v1/customers/{customer_id}/orders`
- `POST /api/v1/chat`

All four endpoints require the `X-API-Key` header. Company IDs are derived from that
key and are rejected if supplied in a request body.

Example order request:

```json
{
  "customer_id": 1,
  "external_order_id": "SHOPX-1001",
  "product_name": "Wireless Headphones",
  "amount": "99.00",
  "status": "processing"
}
```

Example chat request:

```json
{
  "customer_id": 1,
  "order_id": 1,
  "conversation_id": null,
  "message": "Where is my order?"
}
```

The support service currently uses deterministic intent detection and a safe fallback.
A future provider should implement the `SupportProvider` protocol in
`app/services/support_ai.py`; API and persistence code do not need to change.

## Admin dashboard API

The company API key also protects these tenant-scoped admin endpoints:

- `GET /api/v1/admin/orders`
- `GET /api/v1/admin/conversations`
- `GET /api/v1/admin/conversations/{conversation_id}`
- `GET /api/v1/admin/escalations`
- `GET /api/v1/admin/escalations/{escalation_id}`
- `PATCH /api/v1/admin/escalations/{escalation_id}`
- `GET /api/v1/admin/analytics`

Escalations support `OPEN`, `IN_PROGRESS`, and `RESOLVED`. Resolving sets
`resolved_at` and marks the conversation `RESOLVED`. The MVP intentionally rejects
reopening a resolved escalation with HTTP 409 so the resolution timestamp remains
consistent.

Example escalation update:

```json
{
  "assigned_agent": "Agent Priya",
  "status": "RESOLVED",
  "human_response": "Your refund has been approved."
}
```

MVP analytics count distinct escalated conversations. AI-resolved conversations are
`total_conversations - human_escalated`, open escalations are all non-`RESOLVED`
escalations, and resolution rate is `ai_resolved / total_conversations * 100` (or zero
when no conversations exist).

## Gemini provider

The optional real AI provider uses the official `google-genai` SDK. Configure it only
in the local `.env`:

```env
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.6-flash
```

When `GEMINI_API_KEY` is set, the provider factory selects `GeminiProvider`; otherwise
the deterministic provider remains active. Gemini receives backend-assembled customer
and order context and returns validated structured JSON. Invalid output, unsupported
intents, unavailable models, authentication errors, quota failures, network failures,
and timeouts automatically fall back to deterministic support behavior.

Backend safety remains authoritative: confidence below 0.70 and sensitive refund,
payment, cancellation, account-security, or lost/damaged delivery requests escalate
regardless of Gemini's recommendation. For `order_status`, the final reply is rebuilt
from the database status so a provider cannot invent or replace it.
