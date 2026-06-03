# Подработка — API

Бэкенд для платформы, соединяющей заказчиков и исполнителей. Заказчик создаёт заявку с адресом — система находит ближайшего свободного исполнителя с нужной профессией и отправляет ему предложение. При отказе предложение автоматически уходит следующему по удалённости.

## 🔗 Приложение

- **Сайт:** https://one-time-work.duckdns.org/
- **Swagger UI (документация API):** https://one-time-work.duckdns.org/docs
- **ReDoc:** https://one-time-work.duckdns.org/redoc

## Стек

- **FastAPI** + **Uvicorn**
- **PostgreSQL** + **SQLAlchemy 2** + **Alembic**
- **JWT** (python-jose, bcrypt с SHA-256 prehash)
- **Docker** + **Docker Compose**
- **GitHub Actions** для CI/CD

## Запуск локально

**Требования:** Python 3.12+, PostgreSQL

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Создай `.env` в корне проекта:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/mydb
SECRET_KEY=your-secret-key
```

Применить миграции и запустить:

```bash
alembic upgrade head
uvicorn main:app --reload
```

Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)

## Запуск через Docker

```bash
cp .env.example .env.docker
# отредактируй .env.docker — выставь SECRET_KEY и CORS_ORIGINS

docker compose up -d
```

Все сервисы (приложение + PostgreSQL) поднимаются вместе, миграции применяются автоматически при старте контейнера.

```bash
docker compose logs -f app   # логи
docker compose down          # остановить
docker compose down -v       # остановить и удалить данные БД
```

## Переменные окружения

| Переменная | Описание | Пример |
|---|---|---|
| `DATABASE_URL` | Строка подключения к PostgreSQL | `postgresql://user:pass@host:5432/db` |
| `SECRET_KEY` | Ключ для подписи JWT. Генерируется один раз: `python -c "import secrets; print(secrets.token_hex(32))"` | `4a7f2c8b...` |
| `CORS_ORIGINS` | Разрешённые источники для CORS | `["https://myapp.com"]` или `["*"]` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Время жизни токена в минутах (по умолчанию 60) | `60` |

## API

Полная документация доступна в Swagger (`/docs`) или ReDoc (`/redoc`) после запуска.

| Префикс | Описание |
|---|---|
| `POST /auth/register` | Регистрация, возвращает JWT |
| `POST /auth/login` | Вход по email + пароль |
| `GET /auth/me` | Профиль текущего пользователя |
| `PATCH /auth/me/location` | Обновить координаты |
| `GET /professions/` | Справочник профессий |
| `POST /orders/` | Создать заказ (только employer) |
| `GET /orders/pending-offers` | Входящие предложения (только worker) |
| `POST /orders/offers/{id}/respond` | Принять или отклонить предложение |
| `PATCH /orders/{id}/complete` | Завершить заказ |
| `POST /reviews/` | Оставить отзыв по завершённому заказу |
| `PUT /workers/me/profile` | Настроить профиль исполнителя |
| `PATCH /workers/me/line` | Выйти на линию / уйти с линии |

### Роли

- **employer** — создаёт заказы, завершает их, оставляет отзывы
- **worker** — выбирает профессию, выходит на линию, принимает заказы

### Авторизация в Swagger

1. Выполни `POST /auth/register` или `POST /auth/login`, скопируй `access_token`
2. Нажми **Authorize** → введи `Bearer <токен>`

## Тесты

```bash
pytest tests/ -v
```

Тесты делятся на три уровня:

- `test_security.py` — юнит-тесты хэширования паролей и JWT (без БД)
- `test_auth_service.py` — юнит-тесты сервиса авторизации с моками
- `test_auth_api.py` — интеграционные тесты HTTP-эндпоинтов (реальная БД, каждый тест откатывается)

## CI/CD

При пуше в `main` GitHub Actions:

1. Поднимает PostgreSQL, применяет миграции, прогоняет тесты
2. Если тесты прошли — подключается к серверу по SSH, делает `git pull` и пересобирает контейнер

Необходимые секреты в настройках репозитория (Settings → Secrets → Actions):

| Секрет | Описание |
|---|---|
| `SSH_HOST` | IP-адрес или домен сервера |
| `SSH_USER` | Пользователь для SSH |
| `SSH_PRIVATE_KEY` | Приватный SSH-ключ для деплоя |
| `SECRET_KEY` | JWT-ключ для production |
| `DATABASE_URL` | Строка подключения для production |
| `CORS_ORIGINS` | Разрешённые CORS-источники |
