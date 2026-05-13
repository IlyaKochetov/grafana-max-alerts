import json
import logging
import time
from json import JSONDecodeError
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError

from app.exceptions import MaxApiError, MaxApiRetryableError, RoutingError, SecurityError
from app.schemas.grafana import GrafanaWebhookPayload
from app.services.dedup import build_group_dedup_key
from app.services.formatter import truncate_message
from app.services.normalizer import normalize_grafana_payload
from app.services.security import verify_webhook_security

logger = logging.getLogger(__name__)
router = APIRouter(tags=["grafana"])


@router.post("/webhooks/grafana")
async def grafana_webhook(request: Request) -> dict[str, Any]:
    started_at = time.perf_counter()
    request_id = str(uuid4())
    settings = request.app.state.settings

    raw_body = await request.body()
    if len(raw_body) > settings.request_body_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Request body too large",
        )

    try:
        verify_webhook_security(request.headers, raw_body, settings)
    except SecurityError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    try:
        raw_payload = json.loads(raw_body)
    except JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from exc

    try:
        payload = GrafanaWebhookPayload.model_validate(raw_payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid Grafana webhook payload",
        ) from exc

    group = normalize_grafana_payload(payload)
    if not group.alerts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No alerts in payload")

    try:
        routes = request.app.state.alert_router.resolve_routes(group)
    except RoutingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    messages_sent = 0
    deduplicated = 0

    for route_config in routes:
        dedup_key = build_group_dedup_key(group, route_config.chat_id)
        if settings.dedup_enabled and await request.app.state.dedup.seen(dedup_key):
            deduplicated += 1
            continue

        text = request.app.state.formatter.format_group(group, route_config.template)
        text = truncate_message(text, settings.max_message_max_length)

        try:
            await request.app.state.max_client.send_message(
                chat_id=route_config.chat_id,
                text=text,
                notify=route_config.notify,
                format=settings.max_message_format,
            )
        except (MaxApiError, MaxApiRetryableError) as exc:
            logger.warning(
                "max_api_send_failed request_id=%s route=%s chat_id=%s error=%s",
                request_id,
                route_config.name,
                route_config.chat_id,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="MAX API request failed",
            ) from exc

        if settings.dedup_enabled:
            await request.app.state.dedup.mark_seen(dedup_key, settings.dedup_ttl_seconds)
        messages_sent += 1

    duration_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info(
        "grafana_webhook_processed request_id=%s status=%s alerts_count=%s routes_count=%s "
        "messages_sent=%s deduplicated=%s duration_ms=%s",
        request_id,
        group.status,
        len(group.alerts),
        len(routes),
        messages_sent,
        deduplicated,
        duration_ms,
    )

    return {
        "status": "accepted",
        "alerts_received": len(group.alerts),
        "messages_sent": messages_sent,
        "deduplicated": deduplicated,
    }
