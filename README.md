# Payment Orchestrator

Сервис проведения платёжной операции через внешнего провайдера с устойчивостью к повторам, конкурентным запросам, потерянным HTTP-ответам и перезапускам.

Финальный статус операции определяется **только** callback-квитанцией. Успешный транспортный ответ провайдера не означает завершение платежа, а отсутствие ответа не означает, что платёж не был создан.

## Стек

- Python 3.14
- FastAPI
- PostgreSQL (SQLAlchemy async + asyncpg)
- Alembic
- httpx
- Docker Compose
- provider-simulator (`ghcr.io/fintech-dev-lab/internship-provider-simulator:v0.2.0`)

## Запуск

```bash
docker compose up --build
```

Сервисы:

| Сервис             | Адрес                 |
|--------------------|-----------------------|
| candidate-service  | http://localhost:8080 |
| provider-simulator | http://localhost:8081 |
| PostgreSQL         | localhost:5432        |

Проверка готовности:

```bash
curl http://localhost:8080/health
```

Ответ:

```json
{"status":"ok"}
```

Остановка:

```bash
docker compose down
```

Данные PostgreSQL сохраняются в Docker volume и переживают пересоздание контейнеров.

## API

| Метод  | Маршрут                   | Описание                       |
|--------|---------------------------|--------------------------------|
| `GET`  | `/health`                 | Проверка готовности            |
| `POST` | `/operations`             | Создание операции              |
| `POST` | `/operations/{id}/submit` | Надёжно запланировать отправку |
| `POST` | `/receipts`               | Принять callback-квитанцию     |
| `GET`  | `/operations/{id}`        | Текущее состояние операции     |
| `GET`  | `/operations/{id}/events` | История переходов              |

### Состояния

`CREATED` → `PROCESSING` → `COMPLETED` | `REJECTED`

- **CREATED** — операция создана, отправка ещё не запрошена
- **PROCESSING** — намерение отправки сохранено, ожидается результат провайдера
- **COMPLETED** / **REJECTED** — подтверждено только callback-квитанцией

## Полный сквозной сценарий

### 1. Создать операцию

```bash
curl -X POST http://localhost:8080/operations \
  -H "Content-Type: application/json" \
  -d '{
    "operationId": "operation-demo-1",
    "amount": "1000.00",
    "currency": "RUB",
    "description": "Оплата заказа"
  }'
```

Ожидание: **201 Created**

```json
{
  "operationId": "operation-demo-1",
  "amount": "1000.00",
  "currency": "RUB",
  "description": "Оплата заказа",
  "status": "CREATED",
  "providerPaymentId": null
}
```

Повторное создание с тем же `operationId` → **409 Conflict**.

### 2. Отправить (submit)

```bash
curl -X POST http://localhost:8080/operations/operation-demo-1/submit
```

Ожидание: **202 Accepted**, статус `PROCESSING`.  
После ответа провайдера в операции появляется `providerPaymentId`.

Повторный submit → **200 OK** и текущее состояние (второе намерение не создаётся).

### 3. Дождаться callback

Симулятор сам вызывает `POST /receipts`. Через 1–2 секунды:

```bash
curl http://localhost:8080/operations/operation-demo-1
```

Ожидание: `"status": "COMPLETED"` (режим success у симулятора).

### 4. История событий

```bash
curl http://localhost:8080/operations/operation-demo-1/events
```

Ожидание: переходы `CREATED` → `PROCESSING` → `COMPLETED`.

## Дополнительные сценарии

### Идемпотентность submit

```bash
curl -X POST http://localhost:8080/operations/operation-demo-1/submit
curl -X POST http://localhost:8080/operations/operation-demo-1/submit
```

Все повторные запросы возвращают **200** и не создают новый платёж у провайдера.

### Recovery после недоступности провайдера

```bash
# Остановить провайдера
docker compose stop provider-simulator

# Создать операцию и выполнить submit
curl -X POST http://localhost:8080/operations \
  -H "Content-Type: application/json" \
  -d '{"operationId":"operation-recovery-1","amount":"50.00","currency":"RUB","description":"Recovery"}'

curl -X POST http://localhost:8080/operations/operation-recovery-1/submit
# → 202, status=PROCESSING, providerPaymentId=null

# Поднять провайдера и перезапустить сервис
docker compose start provider-simulator
docker compose restart candidate-service

# Проверить результат
curl http://localhost:8080/operations/operation-recovery-1
curl http://localhost:8080/operations/operation-recovery-1/events
```

Ожидание: операция доведена до `COMPLETED`, в истории есть все три перехода.

### Поведение при сетевых ошибках

При 503 и сетевых сбоях сервис:

- оставляет операцию в `PROCESSING`
- повторяет вызов с тем же `Idempotency-Key`
- использует ограниченный exponential backoff с jitter
- продолжает незавершённые операции при старте (recovery)

## Как это устроено

1. `POST /operations` создаёт операцию и событие `CREATED`.
2. `POST /operations/{id}/submit` атомарно переводит операцию в `PROCESSING` (`SELECT FOR UPDATE`) и только после фиксации намерения вызывает провайдера.
3. Вызов провайдера выполняется с заголовками:
   - `Idempotency-Key: {operationId}`
   - `X-Correlation-ID: {operationId}`
4. Ответ `202` от провайдера сохраняет `providerPaymentId`, но **не** переводит операцию в финальный статус.
5. `POST /receipts` в одной транзакции выставляет `COMPLETED` или `REJECTED` и пишет событие.
6. При старте приложения выполняется recovery всех операций в статусе `PROCESSING`.

## Миграции

Обычно таблицы создаются через Alembic. При необходимости вручную:

```bash
docker compose run --rm \
  -e POSTGRES_HOST=db \
  -e POSTGRES_USER=payments \
  -e POSTGRES_PASSWORD=payments \
  -e POSTGRES_DB=payments \
  -e POSTGRES_PORT=5432 \
  candidate-service alembic upgrade head
```

## Переменные окружения

| Переменная          | Описание        | Значение в Compose               |
|---------------------|-----------------|----------------------------------|
| `PROVIDER_URL`      | URL провайдера  | `http://provider-simulator:8081` |
| `POSTGRES_HOST`     | Хост БД         | `db`                             |
| `POSTGRES_PORT`     | Порт БД         | `5432`                           |
| `POSTGRES_USER`     | Пользователь БД | `payments`                       |
| `POSTGRES_PASSWORD` | Пароль БД       | `payments`                       |
| `POSTGRES_DB`       | Имя БД          | `payments`                       |


## Структура проекта

```text
app/
  api/          # HTTP-роуты
  common/       # enums
  models/       # SQLAlchemy-модели
  schemas/      # Pydantic-схемы
  services/     # бизнес-логика, provider client, recovery
  config.py
  db.py
  main.py
logs/
tests/
alembic/        # миграции
docker-compose.yml
Dockerfile
requirements.txt
README.md
```

## Логи

Сервис пишет структурные логи в JSON.

- консоль: `docker compose logs candidate-service`
- файлы: каталог `logs/` (ротация раз в сутки, хранение 30 дней)

Пример поиска по операции:

```bash
# Linux / Git Bash
grep log-demo-1 logs/app.log

# или
docker compose logs candidate-service | grep log-demo-1
