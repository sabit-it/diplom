from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from api.auth import router as auth_router
from api.messages import router as messages_router
from api.offers import router as offers_router
from api.orders import router as orders_router
from api.professions import router as professions_router
from api.reviews import router as reviews_router
from api.workers import router as workers_router

OPENAPI_DESCRIPTION = """
## API сервиса подработки

Бэкенд для взаимодействия **заказчиков** и **исполнителей**: регистрация, вход по JWT, геолокация, справочник профессий, профиль исполнителя и режим «на линии», создание заказов и диспетчеризация ближайшему онлайн‑работнику с той же профессией.

### Авторизация в Swagger
1. Выполните `POST /auth/register` или `POST /auth/login` и скопируйте `access_token`.
2. Нажмите **Authorize**, в поле введите: `Bearer <ваш_токен>` (слово Bearer и пробел обязательны).
3. Либо используйте `POST /auth/token` (OAuth2): в поле **username** укажите **email**, в **password** — пароль.

### Роли
- **employer** — создаёт заказы (`POST /orders/`), завершает заказ (`PATCH /orders/{order_id}/complete`), смотрит карточку заказа, оставляет отзывы.
- **worker** — настраивает профиль (`PUT /workers/me/profile`), координаты (`PATCH /auth/me/location`), выходит на линию (`PATCH /workers/me/line`), получает предложения (`GET /orders/pending-offers`), отвечает на них (`POST /orders/offers/{offer_id}/respond`).

### Профессии
Список активных услуг: **`GET /professions/`** (и **`GET /professions/{id}`**). У каждой записи есть **`hourly_rate`** (число из прайса) и **`rate_unit`**: почасовая (`hour`), за м² (`square_meter`), за створку окна (`window_sash`).  
В **`POST /orders/`** поле **`profession_id`** должно совпадать с **активной** записью справочника; иначе вернётся ошибка. Поля **`hours`** и **`hourly_rate`** в заказе задают итог **`total_price`** — их интерпретация (часы, метры и т.д.) согласуется на стороне клиента с подсказкой из справочника.

### Исполнитель: профиль и линия
1. **`PUT /workers/me/profile`** — выбор **`profession_id`** из справочника (только активные).  
2. **`PATCH /auth/me/location`** — передать **`lat`**, **`lng`** (нужны, чтобы выйти на линию и участвовать в подборе по гео).  
3. **`PATCH /workers/me/line`** с **`"is_online": true`** — исполнитель в очереди на заказы с той же профессией; **`false`** — не получает новые предложения.

### Заказы и гео
После **`POST /orders/`** система ищет ближайшего исполнителя с тем же **`profession_id`**, у кого **`is_online`**, есть координаты (профиль или пользователь) и не расходится профессия. При отказе предложение уходит следующему по удалённости. После принятия участники могут **`PATCH /orders/{order_id}/complete`** → статус **`completed`**, затем отзывы **`POST /reviews/`**.

### Email‑уведомления
На ключевых событиях участникам автоматически уходят письма: исполнителю — при новом предложении, заказчику — при принятии, отказе или отсутствии кандидатов, обоим — при завершении заказа. Работает при наличии `SMTP_USER` и `SMTP_PASSWORD` в окружении; при их отсутствии уведомления молча пропускаются.

### Ограничения текущей версии
Теги **«Сообщения»** и **«Отклики»** — заготовки без HTTP‑операций (в списке операций не отображаются).
""".strip()

OPENAPI_TAGS = [
    {
        "name": "Обзор",
        "description": "Служебная проверка доступности API.",
    },
    {
        "name": "Авторизация",
        "description": (
            "Регистрация, вход, выдача JWT, профиль текущего пользователя, "
            "обновление координат (ручное и «живое» с уменьшением шума при стоянии на месте)."
        ),
    },
    {
        "name": "Заказы",
        "description": (
            "Создание заказа (только **активный** `profession_id` из `GET /professions/`), диспетчеризация ближайшему "
            "исполнителю на линии с той же профессией, входящие предложения, принять/отказать, карточка заказа, "
            "завершение `PATCH .../complete` перед отзывами."
        ),
    },
    {
        "name": "Сообщения",
        "description": "Чат по заказу (в разработке).",
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
            "Профиль исполнителя с выбором профессии из справочника и переключатель «на линии» "
            "(готов принимать заказы по гео или нет)."
        ),
    },
]

app = FastAPI(
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


@app.get(
    "/",
    tags=["Обзор"],
    summary="Проверка сервиса",
    description="Возвращает текстовую метку, что HTTP‑сервис запущен. Авторизация не требуется.",
)
def home():
    return "hello world"
