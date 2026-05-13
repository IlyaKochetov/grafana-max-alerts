# PLAN.md — grafana-max-alerts

> Рабочий план реализации. Написан на основе `01_PROJECT_LOGIC.md` и `02_TECHNICAL_IMPLEMENTATION.md`.
> Цель: MVP → production-ready сервис поэтапно, без раздувания скоупа.

---

## Состояние проекта

- [x] Документы логики и технической реализации написаны
- [x] Код MVP написан

---

## Архитектурные решения, принятые до старта

| Решение | Выбор | Причина |
|---|---|---|
| Web framework | FastAPI | async, нативный Pydantic, удобен для webhook |
| Python | 3.12+ | `type hints`, `match`, последние stdlib |
| Package manager | uv | скорость, lock-файл |
| HTTP client | httpx (async) | нативный async, удобен с respx для тестов |
| Config | pydantic-settings + YAML | env — секреты, YAML — роутинг |
| Templates | Jinja2 | расширяемость, разделение логики и вывода |
| Retry | tenacity | декларативный, гибкий |
| Logging | structlog или stdlib + JSON | JSON в prod, читаемые в dev |
| Tests | pytest + pytest-asyncio + respx | стандарт |
| Linting | ruff + mypy (strict) | скорость + типобезопасность |

**Ключевые инварианты кода:**
- Никакой бизнес-логики в endpoint — только orchestration
- MAX API только через `MaxClient`
- Все настройки только через `Settings`
- Секреты не попадают в логи никогда
- Тесты не ходят в реальный MAX API

---

## Структура проекта (целевое состояние)

```
grafana-max-alerts/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory, lifespan
│   ├── config.py                # Settings (pydantic-settings) + yaml loader
│   ├── logging_config.py        # structlog / JSON formatter setup
│   ├── exceptions.py            # AppError, SecurityError, MaxApiError, ...
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py            # GET /health, GET /ready
│   │   └── grafana.py           # POST /webhooks/grafana
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── grafana.py           # GrafanaAlert, GrafanaWebhookPayload
│   │   ├── normalized.py        # AlertEvent, AlertGroup
│   │   └── max_api.py           # SendMessageRequest, SendMessageResult
│   ├── services/
│   │   ├── __init__.py
│   │   ├── normalizer.py        # normalize_grafana_payload()
│   │   ├── formatter.py         # MessageFormatter, truncate_message()
│   │   ├── max_client.py        # MaxClient (async httpx)
│   │   ├── router.py            # AlertRouter, RouteConfig
│   │   ├── dedup.py             # DedupStore, InMemoryDedupStore
│   │   └── security.py          # verify_shared_secret(), verify_hmac()
│   └── templates/
│       ├── firing.md.j2
│       ├── resolved.md.j2
│       └── group.md.j2
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── grafana_webhook_firing.json
│   │   └── grafana_webhook_resolved.json
│   ├── test_health.py
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
├── Makefile
├── README.md
└── PLAN.md                      # этот файл
```

---

## Этапы реализации

### Этап 1 — Bootstrap

**Цель:** проект запускается, /health отвечает, тесты проходят.

**Файлы:**
- `pyproject.toml` — зависимости, ruff, mypy
- `app/main.py` — FastAPI app factory с lifespan
- `app/config.py` — `Settings` через `pydantic-settings`, все env из `.env.example`
- `app/logging_config.py` — JSON formatter в prod, обычный в dev
- `app/exceptions.py` — иерархия исключений
- `app/api/health.py` — `GET /health` (200 ok) + `GET /ready` (проверка конфига)
- `.env.example`
- `tests/test_health.py`

**Критерии готовности:**
- `uv run uvicorn app.main:app --reload` — запускается без ошибок
- `GET /health` → `{"status": "ok"}`
- `GET /ready` → `{"status": "ready"}` если конфиг корректен
- `uv run pytest tests/test_health.py` — зелёный
- `uv run mypy app/` — без ошибок
- `uv run ruff check app/` — без ошибок

**Статус:** реализовано.

---

### Этап 2 — Grafana schemas + нормализация

**Цель:** уметь разобрать Grafana payload и получить нормализованные модели.

**Файлы:**
- `app/schemas/grafana.py` — `GrafanaAlert`, `GrafanaWebhookPayload`
- `app/schemas/normalized.py` — `AlertEvent`, `AlertGroup`
- `app/services/normalizer.py` — `normalize_grafana_payload()` + `stable_hash()`
- `tests/fixtures/grafana_webhook_firing.json`
- `tests/fixtures/grafana_webhook_resolved.json`
- `tests/test_normalizer.py`

**Правила нормализации (приоритеты):**

| Поле | Источники по приоритету |
|---|---|
| `alertname` | `alert.labels["alertname"]` → `payload.commonLabels["alertname"]` → `payload.title` → `"Unnamed alert"` |
| `severity` | `alert.labels["severity"]` → `payload.commonLabels["severity"]` → `None` |
| `service` | `labels["service"]` → `labels["app"]` → `labels["job"]` → commonLabels теми же ключами → `None` |
| `environment` | `labels["env"]` → `labels["environment"]` → commonLabels → `None` |
| `fingerprint` | `alert.fingerprint` → `stable_hash(status + labels + annotations + startsAt)` |
| `group_key` | `payload.groupKey` → `stable_hash(receiver + status + groupLabels + commonLabels)` |
| `ends_at` | `None` если значение `0001-01-01T00:00:00Z` (Grafana заглушка для firing) |

**Критерии готовности:**
- Парсинг firing + resolved payload из fixture — без ошибок
- Поле `fingerprint` никогда не случайное
- `endsAt = 0001-01-01T00:00:00Z` → `ends_at = None`
- Пустой `alerts` в payload поднимает ошибку (или AlertGroup с пустым списком — обработать на уровне endpoint)
- Покрытие: нет alertname, нет fingerprint, несколько alerts, mixed status

**Статус:** реализовано.

---

### Этап 3 — Formatter + шаблоны

**Цель:** из `AlertGroup` получить готовый текст для MAX.

**Файлы:**
- `app/templates/firing.md.j2`
- `app/templates/resolved.md.j2`
- `app/templates/group.md.j2`
- `app/services/formatter.py` — `MessageFormatter`, `truncate_message()`
- `tests/test_formatter.py`

**Шаблоны:**

*Один firing alert:*
```
🔥 FIRING: High CPU usage

Service: samolet
Instance: app-01
Severity: critical
Started: 2026-05-13 18:20 MSK

CPU usage is above 90% for 5 minutes.

Dashboard: https://...
Panel: https://...
Silence: https://...
Runbook: https://...
```

*Один resolved alert:*
```
✅ RESOLVED: High CPU usage

Service: samolet
Instance: app-01
Duration: 11m 42s
Resolved: 2026-05-13 18:32 MSK
```

*Группа:*
```
🔥 FIRING: 3 alerts

1. High CPU usage
   service=samolet instance=app-01 severity=critical

2. Redis down
   service=vkino instance=redis-01 severity=critical

+2 more alerts

⚠️ Grafana truncated 2 alerts in this notification.

Dashboard: https://...
```

**truncate_message:** обрезать до `max_length - len("\n\n... truncated")`, добавить суффикс.

**Критерии готовности:**
- firing содержит 🔥, resolved содержит ✅
- Сообщение > лимита обрезается, оканчивается на `... truncated`
- `truncatedAlerts > 0` отображается в группе
- Нет паники если поля `None`

**Статус:** реализовано.

---

### Этап 4 — Security

**Цель:** webhook защищён, секреты не утекают.

**Файл:** `app/services/security.py`

**Режим 1 (MVP) — shared secret:**
- Ожидать заголовок `X-Webhook-Secret`
- Сравнивать через `hmac.compare_digest` (constant-time)
- Если `GRAFANA_WEBHOOK_SECRET` не задан — пропускать всё (dev mode)

**Режим 2 (post-MVP) — HMAC-SHA256:**
- Raw body → HMAC-SHA256 с `GRAFANA_HMAC_SECRET`
- Если задан `GRAFANA_HMAC_TIMESTAMP_HEADER`: взять timestamp, проверить age <= `GRAFANA_HMAC_MAX_AGE_SECONDS`, подписываемая строка: `timestamp:body`
- Сравнивать через `hmac.compare_digest`
- HMAC считать по **raw body**, не по re-serialized JSON

**Критерии готовности:**
- Правильный секрет → проходит
- Неправильный → `SecurityError`
- `None` секрет → проходит (dev)
- Нет timing attack через `==`

**Статус:** реализовано.

---

### Этап 5 — MAX client

**Цель:** надёжная отправка сообщений в MAX с retry.

**Файл:** `app/services/max_client.py`

**API:**
```
POST https://platform-api.max.ru/messages?chat_id={chat_id}
Authorization: {token}
Content-Type: application/json

{"text": "...", "format": "markdown", "notify": true}
```

**Retry-стратегия:**
- Retry: 429, 500, 502, 503, 504, сетевые ошибки, timeout
- No retry: 400, 401, 403, 404
- 3 попытки, exponential backoff, начало с 1 сек

**Критерии готовности:**
- Успешная отправка → `SendMessageResult(message_id=..., raw=...)`
- 401 → `MaxApiError` без retry
- 429 → retry, потом `MaxApiRetryableError`
- Timeout → retry
- Тесты через `respx` (без реального MAX API)

**Статус:** реализовано.

---

### Этап 6 — Router

**Цель:** выбрать правильный чат для каждой группы алертов.

**Файл:** `app/services/router.py`

**Алгоритм:**
1. Собрать labels каждого alert: `common_labels` + `alert.labels` (alert имеет приоритет)
2. Для каждого route проверить, совпадают ли **все** пары в `route.match`
3. Если хоть один alert в группе совпал — route активен
4. Стратегия: all matching routes, но дедупликация по `chat_id`
5. Если ни один route не сработал — default route
6. Если нет default route и нет `MAX_DEFAULT_CHAT_ID` — `RoutingError`

**Критерии готовности:**
- default route если нет совпадений
- match by severity, service, env
- дубли chat_id → одно сообщение
- YAML конфиг парсится в `list[RouteConfig]`
- `config.yaml` опционален — без него работает только с `MAX_DEFAULT_CHAT_ID`

**Статус:** реализовано.

---

### Этап 7 — Deduplication

**Цель:** не дублировать сообщения при повторных webhook.

**Файл:** `app/services/dedup.py`

**Ключ дедупликации:**
```python
stable_hash(f"{route_chat_id}:{group.group_key}:{','.join(sorted(f'{a.fingerprint}:{a.status}' for a in group.alerts))}")
```

**InMemoryDedupStore:**
- TTL per key, хранить `{key: expires_at}` в dict
- `seen()` → проверить, не истёк ли ключ
- `mark_seen()` → записать с expires_at
- `clear()` для тестов
- Периодическая очистка истёкших ключей (при каждом `mark_seen`)

**Критерии готовности:**
- Первый вызов → not seen
- Второй вызов до TTL → seen
- Вызов после TTL → not seen
- `DEDUP_ENABLED=false` — dedup отключается полностью
- Тесты с явным управлением временем (mock time)

**Статус:** реализовано.

---

### Этап 8 — Webhook endpoint

**Цель:** собрать все слои в рабочий endpoint.

**Файл:** `app/api/grafana.py`

**Flow:**
```
raw_body = await request.body()
→ проверить размер (413 если > REQUEST_BODY_MAX_BYTES)
→ verify_webhook_security(headers, raw_body)  # 401 если провал
→ json.loads(raw_body)  # 400 если невалидный JSON
→ GrafanaWebhookPayload.model_validate(...)  # 422 если невалидный payload
→ normalize_grafana_payload(payload)
→ если group.alerts пуст → 400
→ alert_router.resolve_routes(group)
→ для каждого route:
    → build_group_dedup_key(group, route.chat_id)
    → если dedup.seen → deduplicated++; continue
    → formatter.format_group(group)
    → truncate_message(text, settings.max_message_max_length)
    → await max_client.send_message(...)
    → dedup.mark_seen(...)
    → sent++
→ return {"status": "accepted", "alerts_received": N, "messages_sent": N, "deduplicated": N}
```

**Логирование каждого запроса:**
- `request_id` (UUID или ULID)
- `status`, `alerts_count`, `routes_count`, `messages_sent`, `deduplicated`, `duration_ms`
- Ошибки MAX API — warning, не error (отдельная обработка)

**Критерии готовности:**
- Happy path с fixture → accepted
- Неверный secret → 401
- Битый JSON → 400
- Слишком большое тело → 413
- MAX API 500 → логируется, возвращается 502
- MAX API 401 → логируется, возвращается 502
- Интеграционный тест через `TestClient` с mock MAX API (respx)

**Статус:** реализовано.

---

### Этап 9 — Docker + docs

**Цель:** проект готов к deployment и понятен новому пользователю.

**Файлы:**
- `Dockerfile` — multi-stage, python:3.12-slim, uv
- `docker-compose.yml` — bind `127.0.0.1:8000:8000`, volume config.yaml
- `.env.example` — все переменные с комментариями
- `config.example.yaml` — примеры routes
- `Makefile` — `make dev`, `make test`, `make lint`, `make build`, `make up`, `make down`
- `README.md` — полное руководство

**README обязан содержать:**
1. Что делает проект (2-3 предложения)
2. Схема потока: Grafana → сервис → MAX
3. Quickstart за 5 шагов
4. Как создать MAX-бота и получить token
5. Как узнать chat_id
6. Как настроить `.env`
7. Как запустить: `docker compose up -d`
8. Как настроить Grafana Contact Point (скриншот или описание)
9. Пример curl для теста
10. Пример сообщения в MAX
11. Security notes
12. Troubleshooting: топ-5 проблем

**Критерии готовности:**
- `docker compose up --build` — запускается
- `GET /health` через curl → ok
- README: любой devops разворачивает за 10-15 минут

**Статус:** реализовано, Docker запуск требует локальной проверки в окружении с Docker.

---

## Приоритеты по версиям

### MVP (Этапы 1–9)
- [x] Всё выше. Один дефолтный chat_id. Shared secret. In-memory dedup.

### v0.2
- [x] Роутинг по labels (`config.yaml`)
- [x] Разные шаблоны firing/resolved/group
- [x] Retry в MaxClient через tenacity
- [x] Structured JSON logs через stdlib formatter
- [x] Unit-тесты основных сервисов

### v1.0
- [x] HMAC-подпись Grafana (Этап 4, Режим 2)
- [ ] Redis-backend для dedup
- [ ] Prometheus endpoint `/metrics`
- [ ] Примеры systemd + nginx

---

## Риски и контрмеры

| Риск | Контрмера |
|---|---|
| MAX API меняется | MaxClient изолирован, остальной код не знает деталей API |
| Разные версии Grafana payload | `extra="allow"` в Pydantic, fallback-значения, raw payload только в debug |
| Спам в чат | dedup по fingerprint + group_key, `notify=false` для dev/warning |
| Секреты в логах | middleware для фильтрации заголовков, секреты не в startup logs |
| `endsAt = 0001-01-01T00:00:00Z` | нормализовать в `None` на уровне normalizer |

---

## Важные детали реализации

### Зависимости через DI

Инициализировать `MaxClient`, `AlertRouter`, `MessageFormatter`, `DedupStore` один раз в lifespan FastAPI, пробрасывать через `Depends` или глобальный state app.

```python
# app/main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.max_client = MaxClient(...)
    app.state.router = AlertRouter(...)
    app.state.formatter = MessageFormatter(...)
    app.state.dedup = InMemoryDedupStore()
    yield
    await app.state.max_client.close()
```

### httpx client — не создавать на каждый запрос

`MaxClient` должен держать `httpx.AsyncClient` открытым. Закрывать в lifespan.

### Pydantic v2 — `model_config = ConfigDict(extra="allow")`

Для Grafana schemas — обязательно. Grafana может добавить новые поля.

### `hmac.compare_digest` — всегда

Для любого сравнения секретов, даже shared secret. Защита от timing attack.

### Fingerprint — детерминированный

`stable_hash` = `hashlib.sha256(canonical_string.encode()).hexdigest()[:16]`. Canonical string строить через `json.dumps(sorted dict)`.

### endsAt

В Grafana, `endsAt = "0001-01-01T00:00:00Z"` означает "алерт ещё активен". Не показывать пользователю. В normalizer:

```python
ZERO_TIME = datetime(1, 1, 1, tzinfo=timezone.utc)
ends_at = alert.endsAt if alert.endsAt and alert.endsAt != ZERO_TIME else None
```

---

## Команды разработки

```bash
# Установка
uv sync --all-extras

# Dev запуск
uv run uvicorn app.main:app --reload --port 8000

# Тесты
uv run pytest

# Линтинг
uv run ruff check app/ tests/
uv run mypy app/

# Форматирование
uv run ruff format app/ tests/

# Docker
docker compose up --build
```

---

## Тест руками после каждого этапа

```bash
# Health
curl http://127.0.0.1:8000/health

# Webhook (после этапа 8)
curl -X POST http://127.0.0.1:8000/webhooks/grafana \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: change-me" \
  -d @tests/fixtures/grafana_webhook_firing.json
```

---

*Обновлять этот файл по ходу реализации: отмечать выполненные этапы, фиксировать отклонения от плана.*
