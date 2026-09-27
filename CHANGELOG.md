# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).

## [Unreleased]

### Fixed

- Нажатие кнопки **Test** в Grafana Contact Point приводило к `422 Unprocessable Entity`: тестовый payload Grafana присылает `values: null` вместо `{}`, что не проходило валидацию Pydantic. Поле `GrafanaAlert.values` теперь `dict[str, Any] | None`, а нормализация подставляет `{}` при отсутствии значения.
- `docker-compose.yml` по ошибке содержал текст `Dockerfile` (инструкции `FROM`, `RUN`, `COPY` и т.д.) вместо описания сервиса compose. Файл переписан как корректный compose-манифест, который собирает образ через `Dockerfile` и пробрасывает порт `8000`.

### Changed

- Шаблон `group.md.j2` переработан: firing- и resolved-алерты группы теперь показываются раздельными блоками, добавлена нумерация firing-алертов и отметка 🆕 для алертов, впервые увиденных активными в данном чате.
- Шаблоны `firing.md.j2` и `resolved.md.j2` упрощены и приведены к единому стилю оформления (заголовок, summary/description, ссылка на панель/дашборд).
- `AlertEvent.description` больше не подставляет `payload.message` как fallback — используется только `annotations.description`, чтобы не дублировать текст, который Grafana и так показывает в summary.

### Added

- Новая логика "новых алертов": сервис хранит в dedup-хранилище ключ `alert-active:{chat_id}:{fingerprint}` с TTL 7 дней и помечает поле `AlertEvent.is_new`, чтобы отличать впервые сработавшие алерты от уже известных активных при повторных grouped-уведомлениях.

## [0.2.0]

### Added

- Роутинг сообщений по labels через `config.yaml` (`routes`, `default_route`).
- Отдельные Jinja2-шаблоны для firing/resolved/group сообщений.
- Retry в `MaxClient` через `tenacity`.
- Structured JSON логирование.
- Базовый набор unit- и интеграционных тестов.

## [0.1.0]

### Added

- MVP: приём Grafana webhook, нормализация payload, отправка сообщений в MAX Bot API.
- Shared-secret защита webhook (`X-Webhook-Secret`), опциональная HMAC-SHA256 проверка по raw body.
- In-memory дедупликация по группе алертов.
- `/health` и `/ready` эндпоинты.
