# grafana-max-alerts

`grafana-max-alerts` принимает webhook-уведомления Grafana Alerting, нормализует alert payload и отправляет читаемые сообщения в MAX через Bot API.

Поток:

```text
Grafana Alerting -> grafana-max-alerts -> MAX Bot API -> chat
```

## Quickstart

1. Создайте MAX-бота и получите bot token.
2. Узнайте `chat_id` целевого личного или группового чата.
3. Скопируйте `.env.example` в `.env` и заполните `MAX_BOT_TOKEN`, `MAX_DEFAULT_CHAT_ID`, `GRAFANA_WEBHOOK_SECRET`.
4. Запустите сервис:

```bash
docker compose up -d --build
```

5. В Grafana создайте Contact Point типа Webhook на URL:

```text
http://<host>:8000/webhooks/grafana
```

Добавьте HTTP header:

```text
X-Webhook-Secret: <GRAFANA_WEBHOOK_SECRET>
```

## Локальная разработка

```bash
uv sync --all-extras
uv run uvicorn app.main:app --reload --port 8000
```

Healthcheck:

```bash
curl http://127.0.0.1:8000/health
```

Readiness:

```bash
curl http://127.0.0.1:8000/ready
```

## Тестовый webhook

```bash
curl -X POST "http://127.0.0.1:8000/webhooks/grafana" \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: change-me" \
  -d @tests/fixtures/grafana_webhook_firing.json
```

Пример сообщения:

```text
🔥 FIRING: High CPU usage

Service: samolet
Instance: app-01
Severity: critical
Started: 2026-05-13 18:20 MSK

CPU usage is above 90% for 5 minutes
```

## Роутинг

По умолчанию используется `MAX_DEFAULT_CHAT_ID`. Для маршрутизации по labels создайте `config.yaml` на основе `config.example.yaml` и при Docker-запуске добавьте read-only volume `./config.yaml:/app/config.yaml:ro`:

```yaml
routes:
  - name: critical-personal
    match:
      severity: critical
    chat_id: 111111111
    notify: true

default_route:
  chat_id: 444444444
  notify: true
```

Правило считается подходящим, если все пары из `match` совпали с labels хотя бы одного alert в группе. Если совпало несколько правил, сервис отправит в каждый уникальный `chat_id`.

## Security Notes

Для MVP поддерживается shared secret в заголовке `X-Webhook-Secret`. Если `GRAFANA_WEBHOOK_SECRET` не задан, проверка отключена для локальной разработки.

Также реализована HMAC-SHA256 проверка по raw body через `GRAFANA_HMAC_SECRET`; при ее включении shared secret не используется.

Секреты и полный raw payload не логируются. Размер тела ограничен `REQUEST_BODY_MAX_BYTES`.

## Проверки качества

```bash
uv run pytest
uv run ruff check app/ tests/
uv run mypy app/
```

## Troubleshooting

- `/ready` возвращает `MAX_BOT_TOKEN is not configured`: заполните `.env`.
- `/ready` возвращает `No default chat or routes configured`: задайте `MAX_DEFAULT_CHAT_ID` или `default_route` в `config.yaml`.
- Webhook возвращает `401`: проверьте `X-Webhook-Secret`.
- Webhook возвращает `502`: MAX API не принял сообщение или временно недоступен, смотрите логи контейнера.
- Сообщения повторяются: увеличьте `DEDUP_TTL_SECONDS` или проверьте, что Grafana не меняет fingerprint/groupKey.
