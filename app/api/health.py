from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import Settings, get_settings

router = APIRouter(tags=["health"])
SettingsDependency = Annotated[Settings, Depends(get_settings)]


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request, settings: SettingsDependency) -> dict[str, Any]:
    if not settings.max_bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "reason": "MAX_BOT_TOKEN is not configured"},
        )

    app_state = request.app.state
    router_ready = hasattr(app_state, "alert_router") and (
        settings.max_default_chat_id is not None or bool(app_state.alert_router.routes)
    )
    if not router_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "reason": "No default chat or routes configured"},
        )

    formatter_ready = hasattr(app_state, "formatter")
    if not formatter_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "reason": "Message templates are not available"},
        )

    return {"status": "ready"}
