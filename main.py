from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from services.offer_expiry import start_expiry_thread


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_expiry_thread()
    yield
from api.auth import router as auth_router
from api.employers import router as employers_router
from api.messages import router as messages_router
from api.offers import router as offers_router
from api.orders import router as orders_router
from api.professions import router as professions_router
from api.reviews import router as reviews_router
from api.workers import router as workers_router

OPENAPI_DESCRIPTION = """
## API сервиса подработки

Бэкенд для взаимодействия **заказчиков** и **исполнителей**: регистрация, вход по JWT, редактирование профиля, геолокация, справочник профессий, профиль исполнителя с ограничением по расстоянию, режим «на линии», создание заказов, диспетчеризация ближайшему онлайн‑работнику, чат по заказу.

### Авторизация в Swagger
1. Выполните `POST /auth/register` или `POST /auth/login` и скопируйте `access_token`.
2. Нажмите **Authorize**, в поле введите: `Bearer <ваш_токен>` (слово Bearer и пробел обязательны).
3. Либо используйте `POST /auth/token` (OAuth2): в поле **username** укажите **email**, в **password** — пароль.

### Роли
- **employer** — создаёт заказы (`POST /orders/`), смотрит историю (`GET /orders/my`), повторяет заказ (`POST /orders/{id}/repeat`), завершает (`PATCH .../complete`) или отменяет (`PATCH .../cancel`) заказ, пишет в чат (`POST /messages/{id}`), оставляет отзывы.
- **worker** — настраивает профиль (`PUT /workers/me/profile`), координаты (`PATCH /auth/me/location`), выходит на линию (`PATCH /workers/me/line`), получает предложения (`GET /orders/pending-offers`), отвечает на них (`POST /orders/offers/{offer_id}/respond`), пишет в чат, смотрит историю своих заказов.

### Редактирование профиля
- **`PATCH /auth/me`** — имя, телефон, фото (передавать только нужные поля; `null` очищает поле).
- **`PATCH /auth/me/email`** — смена email, требует `current_password`.
- **`PATCH /auth/me/password`** — смена пароля, требует `current_password` + `new_password` (мин. 8 символов). Ответ 204.

### Профессии
Список активных услуг: **`GET /professions/`** (и **`GET /professions/{id}`**). У каждой записи есть **`hourly_rate`** (число из прайса) и **`rate_unit`**: почасовая (`hour`), за м² (`square_meter`), за створку окна (`window_sash`).
В **`POST /orders/`** поле **`profession_id`** должно совпадать с **активной** записью справочника; иначе вернётся ошибка.

### Исполнитель: профиль, дистанция и линия
1. **`PUT /workers/me/profile`** — выбор **`profession_id`** и необязательные поля: `about`, **`max_distance_km`** (1–500; `null` — без ограничений, dispatch не предложит заказ дальше этого радиуса).
2. **`PATCH /auth/me/location`** — передать **`lat`**, **`lng`** (нужны, чтобы выйти на линию и участвовать в подборе по гео).
3. **`PATCH /workers/me/line`** с **`"is_online": true`** — исполнитель в очереди; **`false`** — не получает новые предложения.

### Заказы и гео
После **`POST /orders/`** система ищет ближайшего свободного онлайн‑исполнителя с той же профессией и известными координатами (исключая тех, чей `max_distance_km` превышен). При отказе или таймауте (30 сек) предложение уходит следующему. Исполнитель может вести только один заказ одновременно.

- **`GET /orders/my`** — история (employer — свои заказы, worker — где был исполнителем); фильтр `?status=`.
- **`POST /orders/{id}/repeat`** — новый заказ с теми же параметрами, сброс `scheduled_at`.
- **`PATCH .../complete`** — завершение (доступно обоим участникам).
- **`PATCH .../cancel`** — отмена employer‑ом; работает на `pending_offer`, `no_workers_available` и **`assigned`** (при отмене assigned исполнителю уходит email).

### Чат
Пока заказ в статусе **`assigned`**, участники могут переписываться: `POST /messages/{order_id}` — отправить; `GET /messages/{order_id}` — история (от новых к старым, cursor‑based пагинация через `?before=<id>&limit=50`).

### Email‑уведомления
Письма уходят автоматически: при новом предложении, принятии, отказе, таймауте, отмене assigned‑заказа, отсутствии кандидатов и завершении. Работает при наличии `SMTP_USER` и `SMTP_PASSWORD` в окружении; при их отсутствии уведомления молча пропускаются.
""".strip()

OPENAPI_TAGS = [
    {
        "name": "Обзор",
        "description": "Служебная проверка доступности API.",
    },
    {
        "name": "Авторизация",
        "description": (
            "Регистрация, вход, выдача JWT, профиль текущего пользователя. "
            "Редактирование профиля (`PATCH /auth/me`), смена email (`PATCH /auth/me/email`, требует текущий пароль), "
            "смена пароля (`PATCH /auth/me/password`). "
            "Обновление координат: ручное (`PATCH /auth/me/location`) и потоковое с шумоподавлением при стоянии (`PUT /auth/me/location/live`)."
        ),
    },
    {
        "name": "Заказы",
        "description": (
            "Создание заказа (только **активный** `profession_id`), диспетчеризация ближайшему свободному исполнителю на линии. "
            "История заказов `GET /orders/my` (фильтр по статусу). Повтор заказа `POST /orders/{id}/repeat`. "
            "Входящие предложения, принять/отказать, карточка заказа. "
            "Завершение `PATCH .../complete` (доступно обоим участникам). "
            "Отмена `PATCH .../cancel`: работает на `pending_offer`, `no_workers_available` и `assigned` "
            "(при отмене assigned исполнителю уходит уведомление)."
        ),
    },
    {
        "name": "Сообщения",
        "description": (
            "Чат по заказу между заказчиком и назначенным исполнителем. "
            "Доступен только пока заказ в статусе **`assigned`**. "
            "`POST /messages/{order_id}` — отправить сообщение (мин. 1, макс. 5000 символов). "
            "`GET /messages/{order_id}` — история от новых к старым; cursor‑based пагинация: "
            "`?before=<message_id>&limit=50` (макс. 100 за запрос)."
        ),
    },
    {
        "name": "Отклики",
        "description": "Дополнительные отклики на заказы (в разработке).",
    },
    {
        "name": "Профессии",
        "description": (
            "Каталог услуг (название, базовая ставка `hourly_rate`, единица `rate_unit`: час / м² / створка). "
            "Только эти идентификаторы допустимы в заказе и в профиле исполнителя, если профессия активна."
        ),
    },
    {
        "name": "Отзывы",
        "description": (
            "Оценка 1–5 и текст по завершённому заказу; пересчёт среднего рейтинга и количества отзывов у исполнителя "
            "в `worker_profiles`."
        ),
    },
    {
        "name": "Исполнители",
        "description": (
            "Каталог исполнителей `GET /workers/` с фильтрами (профессия, рейтинг, онлайн) и пагинацией. "
            "Профиль исполнителя: профессия из справочника, описание `about`, "
            "ограничение расстояния `max_distance_km` (1–500 км; `null` — без ограничений, "
            "dispatch не предложит заказ дальше этого радиуса). "
            "Переключатель «на линии» `PATCH /workers/me/line` — готов принимать заказы по гео или нет."
        ),
    },
    {
        "name": "Заказчики",
        "description": (
            "Профиль заказчика: название компании/ИП (`company_name`) и адрес (`address`). "
            "`GET /employers/me` — получить профиль (404, если ещё не создан). "
            "`PUT /employers/me` — создать или обновить; оба поля необязательны."
        ),
    },
]

app = FastAPI(
    lifespan=lifespan,
    title="Подработка — API",
    description=OPENAPI_DESCRIPTION,
    version="0.1.0",
    openapi_tags=OPENAPI_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(orders_router)
app.include_router(offers_router)
app.include_router(messages_router)
app.include_router(professions_router)
app.include_router(reviews_router)
app.include_router(workers_router)
app.include_router(employers_router)


@app.get(
    "/",
    tags=["Обзор"],
    summary="Проверка сервиса",
    description="Возвращает текстовую метку, что HTTP‑сервис запущен. Авторизация не требуется.",
)
def home():
    return "hello world"
