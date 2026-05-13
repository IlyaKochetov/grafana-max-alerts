# Grafana → MAX Alert Bridge: логика проекта и продуктовая задумка

## 1. Короткое описание

Проект `grafana-max-alerts` — это небольшой production-ready Python-сервис, который принимает webhook-уведомления от Grafana Alerting, нормализует события алертов и отправляет понятные сообщения в MAX через Bot API.

Базовый поток:

```text
Grafana Alerting
    ↓ HTTP webhook JSON
grafana-max-alerts
    ↓ нормализация, фильтрация, шаблоны, роутинг
MAX Bot API
    ↓
личный чат / групповой чат / команда
```

Проект не должен быть просто "скриптом, который пересылает JSON". Правильная ценность — сделать маленький alert-router: безопасный, расширяемый, понятный и удобный для реальной эксплуатации.

---

## 2. Зачем это нужно

У Grafana есть alerting и webhook contact point, но MAX не является стандартной интеграцией Grafana. Значит, нужен адаптер между двумя мирами:

- Grafana говорит языком alert payload.
- MAX говорит языком bot messages.
- Команде нужен не сырой JSON, а короткое сообщение: что сломалось, где, насколько критично и куда нажать.

Цель проекта — превратить шумный технический payload в читаемое уведомление:

```text
🔥 FIRING: High CPU usage

Service: samolet
Instance: ntsok.ru
Severity: critical
Started: 2026-05-13 18:20 Europe/Moscow

CPU usage > 90% for 5m

Dashboard: ...
Panel: ...
Silence: ...
```

И аналогично для восстановления:

```text
✅ RESOLVED: High CPU usage

Service: samolet
Instance: ntsok.ru
Duration: 11m 42s
```

---

## 3. Главная продуктовая идея

Сервис должен быть не "MAX-ботом для Grafana", а промежуточным слоем доставки алертов.

То есть он должен отвечать за:

1. Приём webhook от Grafana.
2. Проверку подлинности запроса.
3. Нормализацию разных вариантов Grafana payload.
4. Преобразование payload в человекочитаемое сообщение.
5. Выбор MAX-чата по labels.
6. Защиту от спама и повторов.
7. Надёжную отправку в MAX.
8. Диагностируемость: логи, healthcheck, метрики.

---

## 4. Почему не отправлять напрямую из Grafana

Теоретически Grafana может отправить webhook почти куда угодно. Но напрямую в MAX это плохая идея:

- Grafana не знает бизнес-логику маршрутизации между чатами.
- Grafana payload не совпадает с форматом MAX `POST /messages`.
- Нужны токены MAX, которые не стоит распихивать по Grafana contact points.
- Нужно ограничение длины сообщений.
- Нужно красиво обрабатывать группы алертов.
- Нужна дедупликация.
- Нужны retry, rate limit и нормальные логи.
- В будущем может понадобиться отправлять не только в MAX, но и в Telegram/Slack/email/другие каналы.

Промежуточный сервис делает систему контролируемой.

---

## 5. Целевая аудитория

### Основной пользователь

Разработчик или devops-инженер, у которого есть:

- Grafana Alerting;
- MAX как рабочий мессенджер;
- несколько сервисов/серверов;
- желание получать алерты в понятном виде.

### Типичные сценарии

1. Личный мониторинг pet/project серверов.
2. Командный чат по проекту.
3. Разделение алертов по сервисам:
   - `service=samolet` → чат Samolet;
   - `service=vkino` → чат VKino;
   - `severity=critical` → личное сообщение ответственному;
   - `env=dev` → тихий dev-чат.
4. Быстрый доступ из сообщения к dashboard, panel, silence, runbook.

---

## 6. Что считается успехом проекта

Проект успешен, если его можно развернуть за 10–15 минут и подключить к Grafana без плясок с бубном.

Минимальный успешный сценарий:

1. Пользователь создаёт MAX-бота и получает token.
2. Пользователь узнаёт `chat_id`.
3. Пользователь запускает сервис через Docker Compose.
4. Пользователь создаёт Grafana Contact Point типа Webhook.
5. Тестовый alert из Grafana приходит в MAX в читаемом виде.
6. В логах сервиса понятно, что произошло.

---

## 7. Scope: что делаем

### MVP

В первой рабочей версии обязательно:

- HTTP endpoint `POST /webhooks/grafana`.
- Проверка простого webhook secret.
- Приём стандартного Grafana webhook payload.
- Поддержка payload с несколькими alert-объектами.
- Отправка сообщения в MAX через Bot API.
- Конфигурация через `.env`.
- Один дефолтный `chat_id`.
- Красивое markdown-сообщение.
- Dockerfile.
- `docker-compose.yml`.
- `GET /health`.
- README с инструкцией подключения Grafana и MAX.

### Версия 0.2

- Роутинг по labels.
- `config.yaml` с правилами маршрутизации.
- Разные шаблоны для `firing` и `resolved`.
- Обрезка сообщений под лимит MAX.
- Retry при временных ошибках MAX API.
- Structured JSON logs.
- Unit-тесты основных сервисов.

### Версия 1.0

- HMAC-проверка подписи Grafana.
- Redis-дедупликация.
- In-memory fallback для дедупликации.
- Prometheus endpoint `/metrics`.
- Метрики:
  - принятые webhook-и;
  - отправленные сообщения;
  - ошибки MAX API;
  - пропущенные дубликаты;
  - длительность обработки.
- Готовые примеры systemd и nginx reverse proxy.
- Интеграционные тесты с mock MAX API.

---

## 8. Non-goals: что не делаем сейчас

Важно не раздуть проект до мамонта, который умер ещё до первого коммита.

В первой версии не нужно:

- Web UI.
- Админка.
- База данных.
- Авторизация пользователей.
- Сложная система ролей.
- Очередь задач как обязательная зависимость.
- Kubernetes manifests как обязательный способ запуска.
- Поддержка всех мессенджеров сразу.
- Двустороннее управление алертами из MAX.
- Полный аналог Alertmanager.

Это может появиться потом, но MVP должен быть маленьким.

---

## 9. Основные сущности

### Alert Event

Нормализованное представление одного алерта.

Поля:

- `status`: `firing` или `resolved`;
- `alertname`;
- `severity`;
- `service`;
- `instance`;
- `environment`;
- `summary`;
- `description`;
- `starts_at`;
- `ends_at`;
- `fingerprint`;
- `generator_url`;
- `dashboard_url`;
- `panel_url`;
- `silence_url`;
- `runbook_url`;
- `labels`;
- `annotations`;
- `values`.

### Alert Group

Группа алертов из одного Grafana webhook payload.

Поля:

- `receiver`;
- `status`;
- `org_id`;
- `group_key`;
- `group_labels`;
- `common_labels`;
- `common_annotations`;
- `external_url`;
- `truncated_alerts`;
- `alerts`.

### Route

Правило выбора MAX-чата.

Пример:

```yaml
routes:
  - name: critical-personal
    match:
      severity: critical
    chat_id: 111111
    notify: true

  - name: samolet-team
    match:
      service: samolet
    chat_id: 222222
    notify: true

  - name: dev-muted
    match:
      env: dev
    chat_id: 333333
    notify: false
```

---

## 10. Поведение при разных статусах

### `firing`

Сообщение должно быть заметным, но не истеричным.

Пример:

```text
🔥 FIRING: High CPU usage

Service: samolet
Instance: app-01
Severity: critical
Started: 2026-05-13 18:20

CPU usage is above 90% for 5 minutes.

Links:
Dashboard: ...
Panel: ...
Silence: ...
Runbook: ...
```

### `resolved`

Сообщение должно явно показывать, что проблема ушла.

Пример:

```text
✅ RESOLVED: High CPU usage

Service: samolet
Instance: app-01
Duration: 11m 42s
Resolved: 2026-05-13 18:32
```

### Mixed payload

Если в одном payload окажутся разные алерты, сервис должен не ломаться.

Правило MVP:

- ориентироваться на `payload.status`;
- каждый alert внутри всё равно форматировать по его собственному `alert.status`;
- если алертов несколько, делать групповое сообщение.

---

## 11. Формат сообщений

MAX ограничивает текст сообщения, поэтому формат должен быть компактным.

Приоритет информации:

1. Статус.
2. Название алерта.
3. Severity.
4. Service.
5. Instance.
6. Summary/description.
7. Время.
8. Ссылки.
9. Labels/values — только если включён verbose mode.

Для больших групп:

```text
🔥 FIRING: 5 alerts

1. High CPU usage
   service=samolet instance=app-01 severity=critical

2. Redis down
   service=vkino instance=redis-01 severity=critical

3. Disk usage high
   service=prometheus instance=monitoring-01 severity=warning

+2 more alerts
```

Если `truncatedAlerts > 0`, обязательно добавить:

```text
⚠️ Grafana truncated N alerts in this notification.
```

---

## 12. Безопасность

Минимальная безопасность:

- endpoint не должен быть публично открытым без секрета;
- MAX token хранится только в env;
- секреты не логируются;
- входящий payload логируется аккуратно, без чувствительных заголовков;
- необработанный JSON не отправляется в MAX целиком;
- endpoint должен иметь лимит размера тела запроса.

Рекомендуемые уровни защиты:

1. Shared secret в URL или заголовке.
2. HMAC-подпись Grafana.
3. Ограничение по IP, если инфраструктура позволяет.
4. Rate limit на endpoint.
5. HTTPS на внешнем контуре.

---

## 13. Надёжность

Сервис должен переживать типичные проблемы:

### MAX API временно недоступен

Поведение:

- сделать retry с backoff;
- залогировать ошибку;
- вернуть Grafana корректный ответ в зависимости от выбранной стратегии.

Для MVP допустимо синхронно ждать отправку и вернуть `502`, если MAX недоступен.

Для production лучше:

- быстро принять webhook;
- положить событие в очередь;
- отправлять асинхронно.

Но очередь не должна быть обязательной в первой версии.

### Дубликаты

Grafana может прислать повторное уведомление. Нельзя превращать чат в пулемёт.

MVP:

- in-memory TTL cache.

Production:

- Redis TTL cache.

Ключ:

```text
{groupKey}:{fingerprint}:{status}
```

TTL по умолчанию:

```text
300 секунд
```

### Превышение длины сообщения

MAX message text ограничен. Сервис должен:

- проверять длину перед отправкой;
- обрезать description/labels;
- добавлять пометку `... truncated`;
- никогда не падать из-за слишком длинного текста.

---

## 14. Роутинг

Роутинг — главная фича, которая делает проект не игрушкой.

Правило:

- берём labels каждого алерта;
- объединяем с commonLabels;
- ищем первое подходящее правило;
- если правила нет, используем default route.

Стратегия MVP:

```text
first match wins
```

Стратегия в будущем:

```text
all matching routes
```

Чтобы не спамить один и тот же чат, если несколько правил совпали, нужно дедуплицировать список получателей.

---

## 15. Конфигурация

Минимальный `.env`:

```env
APP_ENV=production
LOG_LEVEL=INFO

GRAFANA_WEBHOOK_SECRET=change-me

MAX_API_BASE_URL=https://platform-api.max.ru
MAX_BOT_TOKEN=change-me
MAX_DEFAULT_CHAT_ID=123456789

MESSAGE_FORMAT=markdown
MESSAGE_MAX_LENGTH=3900
DEDUP_TTL_SECONDS=300
```

Опциональный `config.yaml`:

```yaml
routes:
  - name: critical-alerts
    match:
      severity: critical
    chat_id: 111111
    notify: true

  - name: samolet
    match:
      service: samolet
    chat_id: 222222
    notify: true

templates:
  default: templates/default.md.j2
  firing: templates/firing.md.j2
  resolved: templates/resolved.md.j2
```

---

## 16. Основные риски

### Риск 1. MAX API меняется

MAX API моложе Telegram Bot API, поэтому нужно держать MAX-клиент изолированным в отдельном модуле.

Плохо:

```python
# отправка MAX размазана по всему проекту
```

Хорошо:

```python
class MaxClient:
    async def send_message(...)
```

### Риск 2. Разные версии Grafana payload

Grafana может менять детали payload или пользователь может включить custom payload.

Решение:

- Pydantic-модели должны быть достаточно строгими для важных полей;
- неизвестные поля не должны ломать обработку;
- использовать fallback-значения;
- сохранять raw payload в debug-логах только при явной настройке.

### Риск 3. Спам в чат

Решение:

- дедупликация;
- группировка;
- `notify=false` для dev/warning;
- лимиты на количество сообщений из одного webhook.

### Риск 4. Секреты в логах

Решение:

- middleware для скрытия чувствительных заголовков;
- не логировать `Authorization`;
- не логировать `MAX_BOT_TOKEN`;
- не писать весь env в startup logs.

---

## 17. MVP acceptance criteria

Проект можно считать готовым для первой версии, если:

- `POST /webhooks/grafana` принимает payload из официального примера Grafana.
- Сервис корректно отправляет сообщение в MAX.
- Поддерживается минимум один `chat_id`.
- При неправильном secret возвращается `401` или `403`.
- При битом JSON возвращается `400`.
- При недоступном MAX API ошибка логируется.
- Есть Dockerfile.
- Есть docker-compose пример.
- Есть `.env.example`.
- Есть README с пошаговой настройкой.
- Есть тесты:
  - парсинг Grafana payload;
  - форматирование firing;
  - форматирование resolved;
  - выбор default route;
  - обработка ошибки MAX API.

---

## 18. Что просить Codex сделать первым

Не просить Codex сразу "сделай весь проект". Лучше дать ему этапы.

### Этап 1

Скелет FastAPI-приложения:

- `pyproject.toml`;
- `app/main.py`;
- `app/config.py`;
- endpoint `/health`;
- endpoint `/webhooks/grafana`;
- `.env.example`;
- тестовый запуск.

### Этап 2

Модели и форматтер:

- Pydantic-модели Grafana payload;
- нормализованные модели alert event;
- markdown formatter;
- unit-тесты.

### Этап 3

MAX client:

- `MaxClient`;
- отправка сообщения;
- retry;
- обработка ошибок;
- тесты через mock/respx.

### Этап 4

Роутинг и конфиг:

- yaml config;
- route matcher;
- default route;
- тесты.

### Этап 5

Production polish:

- Docker;
- compose;
- structured logs;
- health/readiness;
- README.

---

## 19. Словарь проекта

- `Grafana webhook` — HTTP-уведомление от Grafana Alerting.
- `Alert group` — один payload, содержащий один или несколько alert-объектов.
- `Alert event` — нормализованное представление одного алерта.
- `Route` — правило выбора MAX-чата.
- `Dedup` — защита от повторной отправки одинаковых уведомлений.
- `Formatter` — модуль преобразования alert event/group в текст.
- `MAX client` — изолированный клиент для вызовов MAX Bot API.

---

## 20. Ссылки на официальные документы

- Grafana webhook notifier: https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/webhook-notifier/
- Grafana contact points: https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/
- MAX API overview: https://dev.max.ru/docs-api
- MAX send message: https://dev.max.ru/docs-api/methods/POST/messages
- MAX webhook subscriptions: https://dev.max.ru/docs-api/methods/POST/subscriptions
- MAX long polling updates: https://dev.max.ru/docs-api/methods/GET/updates
