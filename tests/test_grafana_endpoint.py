import json
from pathlib import Path

import httpx
import respx
from fastapi.testclient import TestClient

FIXTURE = Path(__file__).parent / "fixtures" / "grafana_webhook_firing.json"


@respx.mock
def test_valid_webhook_returns_accepted(client: TestClient) -> None:
    respx.post("https://platform-api.max.ru/messages").mock(
        return_value=httpx.Response(200, json={"message_id": "m1"})
    )

    response = client.post(
        "/webhooks/grafana",
        content=FIXTURE.read_bytes(),
        headers={"Content-Type": "application/json", "X-Webhook-Secret": "change-me"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "accepted",
        "alerts_received": 1,
        "messages_sent": 1,
        "deduplicated": 0,
    }


def test_invalid_secret_returns_401(client: TestClient) -> None:
    response = client.post(
        "/webhooks/grafana",
        content=FIXTURE.read_bytes(),
        headers={"Content-Type": "application/json", "X-Webhook-Secret": "wrong"},
    )

    assert response.status_code == 401


def test_invalid_json_returns_400(client: TestClient) -> None:
    response = client.post(
        "/webhooks/grafana",
        content=b"{",
        headers={"Content-Type": "application/json", "X-Webhook-Secret": "change-me"},
    )

    assert response.status_code == 400


def test_empty_alerts_returns_400(client: TestClient) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["alerts"] = []

    response = client.post(
        "/webhooks/grafana",
        json=payload,
        headers={"X-Webhook-Secret": "change-me"},
    )

    assert response.status_code == 400


@respx.mock
def test_max_api_error_returns_502(client: TestClient) -> None:
    respx.post("https://platform-api.max.ru/messages").mock(
        return_value=httpx.Response(500, json={"error": "server_error"})
    )

    response = client.post(
        "/webhooks/grafana",
        content=FIXTURE.read_bytes(),
        headers={"Content-Type": "application/json", "X-Webhook-Secret": "change-me"},
    )

    assert response.status_code == 502
