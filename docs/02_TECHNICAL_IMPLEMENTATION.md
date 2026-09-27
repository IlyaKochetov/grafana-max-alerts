# Grafana → MAX Alert Bridge: техническая реализация

## 1. Цель документа

Этот документ — техническое задание для реализации проекта `grafana-max-alerts`.

Код должен быть написан так, будто проект будет реально жить на сервере:

- понятная структура;
- типизация;
- тесты;
- изолированные модули;
- конфигурация через env/yaml;
- нормальные логи;
- безопасная обработка webhook;
- Docker-ready запуск.

---

## 2. Рекомендуемый стек

Основной стек:

```text
Python 3.12+
FastAPI
Uvicorn
Pydantic v2
pydantic-settings
httpx
PyYAML
Jinja2
tenacity
structlog или стандартный logging с JSON formatter
pytest
pytest-asyncio
respx
ruff
mypy
uv
```

Почему так:

- `FastAPI` хорошо подходит для webhook-сервисов.
- `Pydantic` нужен для валидации Grafana payload и config.
- `httpx` удобен для async HTTP-клиента MAX API.
- `Jinja2` пригодится для шаблонов сообщений.
- `tenacity` или собственная retry-обвязка нужна для временных ошибок MAX API.
- `uv` — быстрый менеджер зависимостей и окружения.

---

## 3. Предлагаемая структура проекта

```text
grafana-max-alerts/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── logging_config.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py
│   │   └── grafana.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── grafana.py
│   │   ├── normalized.py
│   │   └── max_api.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── normalizer.py
│   │   ├── formatter.py
│   │   ├── max_client.py
│   │   ├── router.py
│   │   ├── dedup.py
│   │   └── security.py
│   ├── templates/
│   │   ├── firing.md.j2
│   │   ├── resolved.md.j2
│   │   └── group.md.j2
│   └── exceptions.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   └── grafana_webhook_firing.json
│   ├── test_grafana_endpoint.py
│   ├── test_normalizer.py
│   ├── test_formatter.py
│   ├── test_router.py
│   ├── test_dedup.py
│   └── test_max_client.py
├── docs/
│   ├── 01_PROJECT_LOGIC.md
│   └── 02_TECHNICAL_IMPLEMENTATION.md
├── config.example.yaml
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── README.md
└── Makefile
```

---

## 4. HTTP API сервиса

### `GET /health`

Назначение: простой healthcheck для Docker/systemd/nginx.

Ответ:

```json
{
  "status": "ok"
}
```

Не должен проверять внешние зависимости.

---

### `GET /ready`

Назначение: readiness check.

Проверяет:

- загружена конфигурация;
- есть `MAX_BOT_TOKEN`;
- есть default route или `MAX_DEFAULT_CHAT_ID`;
- шаблоны доступны.

Не обязан делать реальный запрос в MAX API на каждый вызов.

Ответ:

```json
{
  "status": "ready"
}
```

Если сервис не готов:

```json
{
  "status": "not_ready",
  "reason": "MAX_DEFAULT_CHAT_ID is not configured"
}
```

HTTP status: `503`.

---

### `POST /webhooks/grafana`

Основной endpoint.

Задачи:

1. Принять raw body.
2. Проверить размер тела.
3. Проверить secret/HMAC.
4. Распарсить JSON.
5. Валидировать Grafana payload.
6. Нормализовать payload.
7. Проверить dedup.
8. Найти routes.
9. Сформировать сообщения.
10. Отправить в MAX.
11. Вернуть понятный результат.

Успешный ответ:

```json
{
  "status": "accepted",
  "alerts_received": 2,
  "messages_sent": 1,
  "deduplicated": 0
}
```

При неверном секрете:

```json
{
  "detail": "Invalid webhook secret"
}
```

HTTP status: `401` или `403`.

При невалидном payload:

```json
{
  "detail": "Invalid Grafana webhook payload"
}
```

HTTP status: `400` или `422`.

---

## 5. Конфигурация

### `../.env.example`

```env
APP_NAME=grafana-max-alerts
APP_ENV=development
LOG_LEVEL=INFO

# Webhook security
GRAFANA_WEBHOOK_SECRET=change-me
GRAFANA_HMAC_SECRET=
GRAFANA_HMAC_HEADER=X-Grafana-Alerting-Signature
GRAFANA_HMAC_TIMESTAMP_HEADER=X-Grafana-Alerting-Timestamp
GRAFANA_HMAC_MAX_AGE_SECONDS=300

# MAX API
MAX_API_BASE_URL=https://platform-api.max.ru
MAX_BOT_TOKEN=change-me
MAX_DEFAULT_CHAT_ID=123456789
MAX_MESSAGE_FORMAT=markdown
MAX_MESSAGE_MAX_LENGTH=3900
MAX_REQUEST_TIMEOUT_SECONDS=10
MAX_RETRY_ATTEMPTS=3
MAX_RETRY_BACKOFF_SECONDS=1

# Routing
ROUTES_CONFIG_PATH=config.yaml

# Deduplication
DEDUP_ENABLED=true
DEDUP_BACKEND=memory
DEDUP_TTL_SECONDS=300

# Server
REQUEST_BODY_MAX_BYTES=1048576
```

---

### `../config.example.yaml`

```yaml
routes:
  - name: critical-personal
    match:
      severity: critical
    chat_id: 111111111
    notify: true
    template: group

  - name: samolet-team
    match:
      service: samolet
    chat_id: 222222222
    notify: true
    template: group

  - name: dev-muted
    match:
      env: dev
    chat_id: 333333333
    notify: false
    template: group

default_route:
  chat_id: 444444444
  notify: true
  template: group

templates:
  firing: app/templates/firing.md.j2
  resolved: app/templates/resolved.md.j2
  group: app/templates/group.md.j2
```

---

## 6. Pydantic-модели Grafana

Файл: `../app/schemas/grafana.py`.

Модели должны выдерживать неизвестные поля. Рекомендуется `extra="allow"` для совместимости.

```python
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


AlertStatus = Literal["firing", "resolved"]


class GrafanaAlert(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: AlertStatus
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: datetime | None = None
    endsAt: datetime | None = None
    generatorURL: str | None = None
    fingerprint: str | None = None
    silenceURL: str | None = None
    dashboardURL: str | None = None
    panelURL: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)


class GrafanaWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    receiver: str | None = None
    status: AlertStatus
    orgId: int | None = None
    alerts: list[GrafanaAlert] = Field(default_factory=list)
    groupLabels: dict[str, str] = Field(default_factory=dict)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    commonAnnotations: dict[str, str] = Field(default_factory=dict)
    externalURL: str | None = None
    version: str | None = None
    groupKey: str | None = None
    truncatedAlerts: int = 0
    title: str | None = None
    state: str | None = None
    message: str | None = None
```

Важно:

- `alerts` может быть пустым только если Grafana/пользователь прислал странный custom payload. В норме это ошибка.
- `endsAt = 0001-01-01T00:00:00Z` для firing не надо показывать пользователю как реальное время завершения.
- `labels` и `annotations` могут не содержать ожидаемых ключей.

---

## 7. Нормализованные модели

Файл: `../app/schemas/normalized.py`.

```python
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


AlertStatus = Literal["firing", "resolved"]


class AlertEvent(BaseModel):
    status: AlertStatus
    alertname: str
    severity: str | None = None
    service: str | None = None
    instance: str | None = None
    environment: str | None = None

    summary: str | None = None
    description: str | None = None
    runbook_url: str | None = None

    starts_at: datetime | None = None
    ends_at: datetime | None = None

    fingerprint: str
    generator_url: str | None = None
    dashboard_url: str | None = None
    panel_url: str | None = None
    silence_url: str | None = None

    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    values: dict[str, Any] = Field(default_factory=dict)


class AlertGroup(BaseModel):
    receiver: str | None = None
    status: AlertStatus
    org_id: int | None = None
    group_key: str
    group_labels: dict[str, str] = Field(default_factory=dict)
    common_labels: dict[str, str] = Field(default_factory=dict)
    common_annotations: dict[str, str] = Field(default_factory=dict)
    external_url: str | None = None
    truncated_alerts: int = 0
    alerts: list[AlertEvent]
```

---

## 8. Нормализация

Файл: `../app/services/normalizer.py`.

Основная функция:

```python
def normalize_grafana_payload(payload: GrafanaWebhookPayload) -> AlertGroup:
    ...
```

Правила:

### `alertname`

Порядок выбора:

1. `alert.labels["alertname"]`
2. `payload.commonLabels["alertname"]`
3. `payload.title`
4. `"Unnamed alert"`

### `severity`

Порядок выбора:

1. `alert.labels["severity"]`
2. `payload.commonLabels["severity"]`
3. `None`

### `service`

Порядок выбора:

1. `alert.labels["service"]`
2. `alert.labels["app"]`
3. `alert.labels["job"]`
4. `payload.commonLabels["service"]`
5. `payload.commonLabels["app"]`
6. `payload.commonLabels["job"]`
7. `None`

### `environment`

Порядок выбора:

1. `alert.labels["env"]`
2. `alert.labels["environment"]`
3. `payload.commonLabels["env"]`
4. `payload.commonLabels["environment"]`
5. `None`

### `fingerprint`

Порядок выбора:

1. `alert.fingerprint`
2. stable hash от `status + labels + annotations + startsAt`

Нельзя делать fingerprint случайным, иначе dedup станет бесполезным.

### `group_key`

Порядок выбора:

1. `payload.groupKey`
2. stable hash от `receiver + status + groupLabels + commonLabels`

---

## 9. Безопасность webhook

Файл: `../app/services/security.py`.

Нужно реализовать два режима.

### Режим 1. Shared secret

Простой режим MVP.

Варианты:

- заголовок `X-Webhook-Secret`;
- query/path параметр не рекомендуется, но можно поддержать для простоты локальной настройки;
- предпочтительно header.

Пример проверки:

```python
def verify_shared_secret(received: str | None, expected: str | None) -> bool:
    if not expected:
        return True
    if not received:
        return False
    return hmac.compare_digest(received, expected)
```

### Режим 2. Grafana HMAC

Grafana умеет подписывать webhook payload через HMAC-SHA256. Реализовать после MVP.

Алгоритм:

1. Взять raw request body.
2. Взять signature из header, например `X-Grafana-Alerting-Signature`.
3. Если настроен timestamp header:
   - взять timestamp;
   - проверить, что timestamp не старше `GRAFANA_HMAC_MAX_AGE_SECONDS`;
   - подписываемая строка: `timestamp + ":" + body`.
4. Если timestamp header не настроен:
   - подписываемая строка: `body`.
5. Посчитать HMAC-SHA256 с shared secret.
6. Сравнить через `hmac.compare_digest`.

Важно: HMAC считать по raw body, а не по повторно сериализованному JSON.

---

## 10. MAX API client

Файл: `../app/services/max_client.py`.

Клиент должен быть изолирован. Остальной код не должен знать детали MAX API.

```python
from dataclasses import dataclass
from typing import Literal

import httpx


TextFormat = Literal["markdown", "html"]


@dataclass(frozen=True)
class SendMessageResult:
    message_id: str | None
    raw: dict


class MaxClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout_seconds: float = 10,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        notify: bool = True,
        format: TextFormat = "markdown",
        disable_link_preview: bool = False,
    ) -> SendMessageResult:
        ...
```

Запрос:

```http
POST https://platform-api.max.ru/messages?chat_id={chat_id}
Authorization: {token}
Content-Type: application/json
```

Body:

```json
{
  "text": "message text",
  "format": "markdown",
  "notify": true
}
```

Нужно поддержать:

- `chat_id`;
- потенциально `user_id` в будущем;
- `notify`;
- `format`;
- `disable_link_preview`.

### Обработка ошибок MAX API

HTTP-коды:

- `200` — успех;
- `400` — неверный запрос, retry не нужен;
- `401` — неверный токен, retry не нужен;
- `404` — чат/ресурс не найден, retry не нужен;
- `429` — rate limit, retry нужен;
- `503` — временная недоступность, retry нужен.

Для retry использовать:

- `429`;
- `500`;
- `502`;
- `503`;
- `504`;
- сетевые ошибки;
- timeout.

Не retry:

- `400`;
- `401`;
- `403`;
- `404`.

---

## 11. Форматирование сообщений

Файл: `../app/services/formatter.py`.

Интерфейс:

```python
class MessageFormatter:
    def format_group(self, group: AlertGroup) -> str:
        ...

    def format_single(self, alert: AlertEvent) -> str:
        ...
```

Рекомендуется Jinja2, но с fallback на простое форматирование.

### Ограничение длины

MAX text limit — до 4000 символов. В config использовать запас:

```text
MAX_MESSAGE_MAX_LENGTH=3900
```

Функция:

```python
def truncate_message(text: str, max_length: int) -> str:
    suffix = "\n\n... truncated"
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix
```

### Экранирование

Если используется Markdown:

- не вставлять неэкранированный пользовательский текст в сложный markdown;
- минимум — не использовать пользовательские labels внутри ссылочного синтаксиса;
- URLs выводить отдельной строкой.

### Шаблон group

`../app/templates/group.md.j2`:

```jinja2
{% if group.status == "firing" %}🔥{% else %}✅{% endif %} **{{ group.status.upper() }}: {{ group.alerts|length }} alert{% if group.alerts|length != 1 %}s{% endif %}**

{% for alert in group.alerts %}
{{ loop.index }}. **{{ alert.alertname }}**
   service={{ alert.service or "-" }} instance={{ alert.instance or "-" }} severity={{ alert.severity or "unknown" }}
   {% if alert.summary %}{{ alert.summary }}{% endif %}
{% endfor %}

{% if group.truncated_alerts > 0 %}
⚠️ Grafana truncated {{ group.truncated_alerts }} alerts in this notification.
{% endif %}

{% set first = group.alerts[0] if group.alerts else None %}
{% if first and first.dashboard_url %}
Dashboard: {{ first.dashboard_url }}
{% endif %}
{% if first and first.panel_url %}
Panel: {{ first.panel_url }}
{% endif %}
{% if first and first.silence_url %}
Silence: {{ first.silence_url }}
{% endif %}
```

---

## 12. Роутинг

Файл: `../app/services/router.py`.

Модели:

```python
from pydantic import BaseModel, Field


class RouteConfig(BaseModel):
    name: str
    match: dict[str, str] = Field(default_factory=dict)
    chat_id: int
    notify: bool = True
    template: str = "group"


class DefaultRouteConfig(BaseModel):
    chat_id: int
    notify: bool = True
    template: str = "group"
```

Интерфейс:

```python
class AlertRouter:
    def resolve_routes(self, group: AlertGroup) -> list[ResolvedRoute]:
        ...
```

Правила MVP:

1. Для каждого alert собрать labels:
   - `group.common_labels`;
   - `alert.labels`, которые имеют приоритет.
2. Проверить route.match:
   - все пары key/value должны совпасть.
3. Если хоть один alert в group совпал с route, group отправляется в этот route.
4. Если ни один route не совпал, использовать default route.
5. Если несколько route ведут в один `chat_id`, отправлять один раз.

Пока использовать `first match wins` или `all matching routes` — лучше `all matching routes`, но с дедупликацией `chat_id`.

---

## 13. Deduplication

Файл: `../app/services/dedup.py`.

Интерфейс:

```python
class DedupStore:
    async def seen(self, key: str) -> bool:
        ...

    async def mark_seen(self, key: str, ttl_seconds: int) -> None:
        ...
```

MVP implementation:

```python
class InMemoryDedupStore(DedupStore):
    ...
```

Ключ:

```python
def build_dedup_key(group: AlertGroup, alert: AlertEvent) -> str:
    return f"{group.group_key}:{alert.fingerprint}:{alert.status}"
```

Для группового сообщения можно использовать:

```python
def build_group_dedup_key(group: AlertGroup, route_chat_id: int) -> str:
    fingerprints = ",".join(sorted(a.fingerprint + ":" + a.status for a in group.alerts))
    return stable_hash(f"{route_chat_id}:{group.group_key}:{fingerprints}")
```

Важно:

- dedup должен быть опциональным;
- для тестов нужен способ очистить storage;
- in-memory dedup не работает между рестартами, это нормально для MVP.

Будущий Redis backend:

```text
SET key 1 EX ttl NX
```

Если команда вернула false — событие уже было.

---

## 14. Endpoint flow

Файл: `../app/api/grafana.py`.

Псевдокод:

```python
@router.post("/webhooks/grafana")
async def grafana_webhook(request: Request) -> WebhookResult:
    raw_body = await request.body()

    if len(raw_body) > settings.request_body_max_bytes:
        raise HTTPException(status_code=413, detail="Request body too large")

    verify_webhook_security(request.headers, raw_body)

    try:
        raw_payload = json.loads(raw_body)
    except JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    try:
        payload = GrafanaWebhookPayload.model_validate(raw_payload)
    except ValidationError:
        raise HTTPException(status_code=422, detail="Invalid Grafana webhook payload")

    group = normalize_grafana_payload(payload)

    if not group.alerts:
        raise HTTPException(status_code=400, detail="No alerts in payload")

    routes = alert_router.resolve_routes(group)

    sent = 0
    deduplicated = 0

    for route in routes:
        dedup_key = build_group_dedup_key(group, route.chat_id)

        if settings.dedup_enabled and await dedup.seen(dedup_key):
            deduplicated += 1
            continue

        text = formatter.format_group(group)
        text = truncate_message(text, settings.max_message_max_length)

        await max_client.send_message(
            chat_id=route.chat_id,
            text=text,
            notify=route.notify,
            format=settings.max_message_format,
        )

        if settings.dedup_enabled:
            await dedup.mark_seen(dedup_key, settings.dedup_ttl_seconds)

        sent += 1

    return {
        "status": "accepted",
        "alerts_received": len(group.alerts),
        "messages_sent": sent,
        "deduplicated": deduplicated,
    }
```

---

## 15. Логирование

Требования:

- JSON logs в production.
- Человеческие logs в development допустимы.
- Каждому webhook присваивать `request_id`.
- Логировать:
  - принятие webhook;
  - количество alerts;
  - group_key;
  - status;
  - resolved routes;
  - ошибки отправки;
  - dedup skip;
  - длительность обработки.

Не логировать:

- `Authorization`;
- `MAX_BOT_TOKEN`;
- webhook secrets;
- полный raw payload по умолчанию.

Пример log event:

```json
{
  "event": "grafana_webhook_processed",
  "request_id": "01HX...",
  "status": "firing",
  "alerts_count": 2,
  "routes_count": 1,
  "messages_sent": 1,
  "deduplicated": 0,
  "duration_ms": 183
}
```

---

## 16. Метрики Prometheus

Не обязательно для MVP, но желательно для версии 1.0.

Endpoint:

```text
GET /metrics
```

Метрики:

```text
grafana_max_webhooks_total{status="accepted|failed"}
grafana_max_alerts_received_total{alert_status="firing|resolved"}
grafana_max_messages_sent_total{chat_id="...", result="success|error"}
grafana_max_dedup_skipped_total
grafana_max_processing_duration_seconds
grafana_max_api_request_duration_seconds
```

Важно: не плодить слишком высокую кардинальность. Например, `chat_id` можно сделать опциональным label или заменить на route name.

---

## 17. Dockerfile

Рекомендуемый вариант:

```dockerfile
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY ../pyproject.toml uv.lock* ./

RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev || uv sync --no-dev

COPY .. .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Если `uv.lock` ещё нет, команда должна не падать. Можно упростить Dockerfile после появления lock-файла.

---

## 18. docker-compose.yml

```yaml
services:
  grafana-max-alerts:
    build: .
    container_name: grafana-max-alerts
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./config.yaml:/app/config.yaml:ro
    ports:
      - "127.0.0.1:8000:8000"
```

Для production лучше закрыть порт наружу и пустить через nginx.

---

## 19. Nginx reverse proxy пример

```nginx
server {
    listen 443 ssl http2;
    server_name alerts.example.com;

    ssl_certificate /etc/letsencrypt/live/alerts.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/alerts.example.com/privkey.pem;

    client_max_body_size 1m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Grafana Contact Point URL:

```text
https://alerts.example.com/webhooks/grafana
```

Header:

```text
X-Webhook-Secret: <secret>
```

---

## 20. systemd unit пример

Если запуск без Docker:

```ini
[Unit]
Description=Grafana MAX Alerts Bridge
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/grafana-max-alerts
EnvironmentFile=/opt/grafana-max-alerts/.env
ExecStart=/usr/local/bin/uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## 21. Тестирование

### Unit tests

Обязательные тесты:

#### Normalizer

- payload с одним firing alert;
- payload с несколькими alerts;
- payload без `alertname`;
- payload без `fingerprint`;
- `endsAt=0001-01-01T00:00:00Z`.

#### Formatter

- firing message содержит 🔥;
- resolved message содержит ✅;
- group message содержит количество alerts;
- message обрезается до лимита;
- `truncatedAlerts > 0` отображается.

#### Router

- default route;
- route by `service`;
- route by `severity`;
- route by `env`;
- дедупликация одинакового `chat_id`.

#### Dedup

- first event is not seen;
- second event is seen;
- expired event becomes not seen.

#### MaxClient

- успешная отправка;
- 401 не retry;
- 429 retry;
- timeout retry;
- malformed response handled.

### API tests

- `GET /health` returns `200`;
- valid webhook returns `accepted`;
- invalid JSON returns `400`;
- invalid secret returns `401/403`;
- too large body returns `413`;
- MAX API error returns expected status/log.

---

## 22. pyproject.toml пример

```toml
[project]
name = "grafana-max-alerts"
version = "0.1.0"
description = "Bridge Grafana Alerting webhooks to MAX messenger bot messages"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.8",
    "pydantic-settings>=2.4",
    "httpx>=0.27",
    "pyyaml>=6.0",
    "jinja2>=3.1",
    "tenacity>=8.5",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
    "ruff>=0.6",
    "mypy>=1.10",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true
```

---

## 23. README: что обязательно описать

README должен содержать:

1. Что делает проект.
2. Схему потока.
3. Быстрый старт.
4. Как создать MAX-бота.
5. Как получить token.
6. Как получить `chat_id`.
7. Как настроить `.env`.
8. Как запустить через Docker Compose.
9. Как настроить Grafana Contact Point.
10. Пример тестового curl.
11. Пример сообщения в MAX.
12. Security notes.
13. Troubleshooting.

---

## 24. Пример curl для локального теста

```bash
curl -X POST "http://127.0.0.1:8000/webhooks/grafana" \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: change-me" \
  -d @tests/fixtures/grafana_webhook_firing.json
```

---

## 25. Пример Grafana payload fixture

Файл: `tests/fixtures/grafana_webhook_firing.json`.

```json
{
  "receiver": "max-webhook",
  "status": "firing",
  "orgId": 1,
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "High CPU usage",
        "service": "samolet",
        "instance": "app-01",
        "severity": "critical",
        "env": "prod"
      },
      "annotations": {
        "summary": "CPU usage is too high",
        "description": "CPU usage is above 90% for 5 minutes",
        "runbook_url": "https://example.com/runbooks/high-cpu"
      },
      "startsAt": "2026-05-13T18:20:00+03:00",
      "endsAt": "0001-01-01T00:00:00Z",
      "generatorURL": "https://grafana.example.com/alerting/rules/1",
      "fingerprint": "abc123",
      "silenceURL": "https://grafana.example.com/alerting/silence/new",
      "dashboardURL": "https://grafana.example.com/d/server/server-overview",
      "panelURL": "https://grafana.example.com/d/server/server-overview?viewPanel=12",
      "values": {
        "A": 93.4
      }
    }
  ],
  "groupLabels": {
    "alertname": "High CPU usage"
  },
  "commonLabels": {
    "service": "samolet",
    "severity": "critical"
  },
  "commonAnnotations": {},
  "externalURL": "https://grafana.example.com/",
  "version": "1",
  "groupKey": "{}:{alertname=\"High CPU usage\"}",
  "truncatedAlerts": 0,
  "title": "[FIRING:1] High CPU usage",
  "state": "alerting",
  "message": "CPU usage is too high"
}
```

---

## 26. Ошибки и исключения

Файл: `app/exceptions.py`.

Рекомендуемые исключения:

```python
class AppError(Exception):
    pass


class SecurityError(AppError):
    pass


class MaxApiError(AppError):
    pass


class MaxApiRetryableError(MaxApiError):
    pass


class RoutingError(AppError):
    pass


class FormattingError(AppError):
    pass
```

На уровне API не отдавать наружу stack trace.

---

## 27. Порядок реализации для Codex

### Step 1. Bootstrap

Сделать:

- `pyproject.toml`;
- базовую структуру `app/`;
- `Settings`;
- `FastAPI app`;
- `/health`;
- `/ready`;
- тесты health.

### Step 2. Grafana schemas

Сделать:

- `GrafanaAlert`;
- `GrafanaWebhookPayload`;
- fixture;
- тесты валидации.

### Step 3. Normalizer

Сделать:

- `AlertEvent`;
- `AlertGroup`;
- `normalize_grafana_payload`;
- stable hash helper;
- тесты.

### Step 4. Formatter

Сделать:

- Jinja2 templates;
- `MessageFormatter`;
- truncate function;
- тесты.

### Step 5. MAX client

Сделать:

- async `MaxClient`;
- retry;
- error mapping;
- tests with `respx`.

### Step 6. Router

Сделать:

- yaml config loader;
- route matcher;
- default route;
- tests.

### Step 7. Webhook endpoint

Собрать всё вместе:

- security check;
- parse;
- normalize;
- route;
- format;
- send;
- response;
- tests.

### Step 8. Docker and docs

Сделать:

- Dockerfile;
- docker-compose;
- `.env.example`;
- `config.example.yaml`;
- README.

---

## 28. Качество кода

Требования:

- type hints везде;
- никакой бизнес-логики внутри FastAPI endpoint, только orchestration;
- MAX API только через `MaxClient`;
- Grafana payload только через schemas/normalizer;
- настройки только через `Settings`;
- нет глобальных mutable-синглтонов без необходимости;
- тесты не ходят в реальный MAX API;
- секреты не попадают в логи.

---

## 29. Возможные будущие фичи

После стабильной версии:

- Redis backend для dedup.
- Очередь задач.
- Несколько notification providers.
- Команды в MAX:
  - `/status`;
  - `/routes`;
  - `/silence`;
  - `/test`.
- Отправка inline-кнопок:
  - Dashboard;
  - Panel;
  - Silence;
  - Runbook.
- Поддержка custom Grafana payload.
- Поддержка Alertmanager-compatible payload.
- Web UI для маршрутов.
- Terraform/Grafana provisioning examples.

---

## 30. Ссылки на официальные документы

- Grafana webhook notifier: https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/webhook-notifier/
- Grafana contact points: https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/
- MAX API overview: https://dev.max.ru/docs-api
- MAX send message: https://dev.max.ru/docs-api/methods/POST/messages
- MAX webhook subscriptions: https://dev.max.ru/docs-api/methods/POST/subscriptions
- MAX long polling updates: https://dev.max.ru/docs-api/methods/GET/updates
