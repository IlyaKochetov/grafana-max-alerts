from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from app.exceptions import MaxApiError, MaxApiRetryableError
from app.schemas.max_api import SendMessageResult, TextFormat

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404}


class MaxClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float = 10,
        retry_attempts: int = 3,
        retry_backoff_seconds: float = 1,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = retry_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        notify: bool = True,
        format: TextFormat = "markdown",
        disable_link_preview: bool = False,
    ) -> SendMessageResult:
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self.retry_attempts),
            wait=wait_exponential(multiplier=self.retry_backoff_seconds, min=0, max=10),
            retry=retry_if_exception(_is_retryable_exception),
            reraise=True,
        )
        try:
            async for attempt in retrying:
                with attempt:
                    return await self._send_message_once(
                        chat_id=chat_id,
                        text=text,
                        notify=notify,
                        format=format,
                        disable_link_preview=disable_link_preview,
                    )
        except MaxApiRetryableError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
            raise MaxApiRetryableError("MAX API request failed after retries") from exc

        raise MaxApiRetryableError("MAX API request failed")

    async def _send_message_once(
        self,
        *,
        chat_id: int,
        text: str,
        notify: bool,
        format: TextFormat,
        disable_link_preview: bool,
    ) -> SendMessageResult:
        response = await self._client.post(
            f"{self.base_url}/messages",
            params={"chat_id": chat_id},
            headers={"Authorization": self.token, "Content-Type": "application/json"},
            json={
                "text": text,
                "format": format,
                "notify": notify,
                "disable_link_preview": disable_link_preview,
            },
        )
        if response.status_code in RETRYABLE_STATUS_CODES:
            raise MaxApiRetryableError(f"MAX API retryable error: {response.status_code}")
        if response.status_code in NON_RETRYABLE_STATUS_CODES or response.is_error:
            raise MaxApiError(f"MAX API error: {response.status_code}")

        raw = _json_or_empty(response)
        return SendMessageResult(message_id=_extract_message_id(raw), raw=raw)


def _is_retryable_exception(exc: BaseException) -> bool:
    return isinstance(
        exc,
        MaxApiRetryableError | httpx.TimeoutException | httpx.NetworkError | httpx.TransportError,
    )


def _json_or_empty(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {"response": payload}


def _extract_message_id(raw: dict[str, Any]) -> str | None:
    for key in ("message_id", "messageId", "id"):
        value = raw.get(key)
        if value is not None:
            return str(value)
    message = raw.get("message")
    if isinstance(message, dict):
        value = message.get("id")
        if value is not None:
            return str(value)
    return None
