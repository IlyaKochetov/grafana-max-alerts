import httpx
import pytest
import respx

from app.exceptions import MaxApiError, MaxApiRetryableError
from app.services.max_client import MaxClient


@pytest.mark.asyncio
@respx.mock
async def test_send_message_success() -> None:
    route = respx.post("https://platform-api.max.ru/messages").mock(
        return_value=httpx.Response(200, json={"message_id": "m1"})
    )
    client = MaxClient(base_url="https://platform-api.max.ru", token="token")

    result = await client.send_message(chat_id=123, text="hello")
    await client.close()

    assert route.called
    assert result.message_id == "m1"


@pytest.mark.asyncio
@respx.mock
async def test_401_does_not_retry() -> None:
    route = respx.post("https://platform-api.max.ru/messages").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )
    client = MaxClient(base_url="https://platform-api.max.ru", token="token")

    with pytest.raises(MaxApiError):
        await client.send_message(chat_id=123, text="hello")
    await client.close()

    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_429_retries_then_fails() -> None:
    route = respx.post("https://platform-api.max.ru/messages").mock(
        return_value=httpx.Response(429, json={"error": "rate_limit"})
    )
    client = MaxClient(
        base_url="https://platform-api.max.ru",
        token="token",
        retry_attempts=2,
        retry_backoff_seconds=0,
    )

    with pytest.raises(MaxApiRetryableError):
        await client.send_message(chat_id=123, text="hello")
    await client.close()

    assert route.call_count == 2
