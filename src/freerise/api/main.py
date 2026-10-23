import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI

from freerise.api import (
    routes_accounts,
    routes_auth,
    routes_cashflow,
    routes_categories,
    routes_cost,
    routes_credentials,
    routes_forecast,
    routes_home,
    routes_insights,
    routes_notifications,
    routes_pension,
    routes_plan,
    routes_plans,
    routes_reconcile,
    routes_reviews,
    routes_settings,
    routes_sync,
    routes_tracking,
    routes_transactions,
    routes_whatif,
)
from freerise.api.deps import current_user
from freerise.config import get_settings
from freerise.db import get_session
from freerise.forecast.attribution import attribute_income

log = logging.getLogger("freerise.api")


def doc_urls(env: str) -> dict:
    """No interactive docs/schema in production."""
    return dict.fromkeys(("docs_url", "redoc_url", "openapi_url")) if env == "production" else {}


def refresh_attribution(app: FastAPI) -> None:
    """Recompute automatic income attribution (the rule may have changed with a deploy)."""
    gen = app.dependency_overrides.get(get_session, get_session)()  # tests: their DB
    try:
        s = next(gen)
        attribute_income(s)
        s.commit()
    except Exception as e:  # noqa: BLE001 - never block startup on it
        log.error("income attribution failed: %s", type(e).__name__)
    finally:
        gen.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    refresh_attribution(app)
    yield


app = FastAPI(title="FreeRise", lifespan=lifespan, **doc_urls(get_settings().env))

protected = APIRouter(dependencies=[Depends(current_user)])
for r in (
    routes_credentials,
    routes_accounts,
    routes_transactions,
    routes_sync,
    routes_categories,
    routes_cashflow,
    routes_plan,
    routes_plans,
    routes_cost,
    routes_whatif,
    routes_forecast,
    routes_pension,
    routes_notifications,
    routes_reconcile,
    routes_settings,
    routes_insights,
    routes_home,
    routes_tracking,
    routes_reviews,
):
    protected.include_router(r.router)

app.include_router(routes_auth.router, prefix="/api")
app.include_router(protected, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}
