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

Пример сообщения (один алерт):

```text
🚨 High CPU usage

CPU usage is above 90% for 5 minutes

[Открыть панель Grafana](https://grafana.example.com/d/abc/panel-1)
```

Кнопкой Grafana **Test** тоже можно пользоваться: поле `values` в тестовом payload приходит как `null`, а не `{}`, и сервис корректно это обрабатывает.

### Групповые сообщения

Если в одной группе несколько алертов, используется шаблон `group.md.j2`: firing и resolved алерты разделяются, а рядом с каждым новым (то есть впервые увиденным для данного chat_id за последние 7 дней) firing-алертом добавляется отметка 🆕:

```text
🚨 **High CPU usage — 2 активных**

**1. 🆕 High CPU usage**
CPU usage is above 90% for 5 minutes

**2. Redis down**
Redis instance is not responding

✅ **Устранено — 1**
Disk usage is above 90%
```

Отметка 🆕 снимается автоматически через 7 дней отсутствия повторных срабатываний (или раньше, если алерт был resolved и снова начал firing).

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
- Webhook возвращает `422` при нажатии кнопки **Test** в Grafana Contact Point: обновите сервис — до фикса `values: null` в тестовом payload не проходило валидацию.

## Changelog

Список изменений — в [CHANGELOG.md](CHANGELOG.md).
