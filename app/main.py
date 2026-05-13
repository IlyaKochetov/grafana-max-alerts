from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.config import get_settings, load_yaml_config
from app.logging_config import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)

    from app.services.dedup import InMemoryDedupStore
    from app.services.formatter import MessageFormatter
    from app.services.max_client import MaxClient
    from app.services.router import AlertRouter, RouterConfig

    yaml_config = load_yaml_config(settings.routes_config_path)
    router_config = RouterConfig.from_settings(settings, yaml_config)

    app.state.settings = settings
    app.state.formatter = MessageFormatter()
    app.state.alert_router = AlertRouter(router_config)
    app.state.dedup = InMemoryDedupStore()
    app.state.max_client = MaxClient(
        base_url=settings.max_api_base_url,
        token=settings.max_bot_token or "",
        timeout_seconds=settings.max_request_timeout_seconds,
        retry_attempts=settings.max_retry_attempts,
        retry_backoff_seconds=settings.max_retry_backoff_seconds,
    )
    try:
        yield
    finally:
        await app.state.max_client.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Grafana MAX Alerts", lifespan=lifespan)
    app.include_router(health_router)

    from app.api.grafana import router as grafana_router

    app.include_router(grafana_router)
    return app


app = create_app()
