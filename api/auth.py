from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_active_user
from models.user import User
from repositories.user_repository import update_user_location
from schemas.auth import (
    EmailChangeRequest,
    LoginRequest,
    PasswordChangeRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserLocationUpdate,
    UserProfileUpdate,
    UserPublic,
)
from services.auth_service import change_email, change_password, login_user, refresh_tokens, register_user, update_profile

router = APIRouter(prefix="/auth", tags=["Авторизация"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация",
    description=(
        "Создаёт нового пользователя с ролью **employer** или **worker**, проверяет уникальность email "
        "и при необходимости телефона, сохраняет хеш пароля и сразу возвращает JWT для дальнейших запросов."
    ),
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return register_user(
        db,
        email=str(payload.email),
        password=payload.password,
        last_name=payload.last_name,
        first_name=payload.first_name,
        patronymic=payload.patronymic,
        role=payload.role.value,
        phone=payload.phone,
        photo_url=payload.photo_url,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Вход (JSON)",
    description=(
        "Аутентификация по email и паролю в теле JSON. Возвращает `access_token` — используйте в заголовке "
        "`Authorization: Bearer ...` для всех защищённых методов."
    ),
)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return login_user(db, payload.email, payload.password)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Обновить токены",
    description=(
        "Принимает `refresh_token` (TTL 30 дней). Возвращает новую пару `access_token` + `refresh_token`. "
        "Используйте, когда `access_token` истёк. Старый `refresh_token` после этого больше не действует "
        "(rotating refresh tokens)."
    ),
)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return refresh_tokens(db, payload)


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Вход (OAuth2 form, для Swagger Authorize)",
    description=(
        "Стандартная форма **application/x-www-form-urlencoded** как в RFC OAuth2 password flow. "
        "Поле **username** в этой схеме означает **email** пользователя; **password** — пароль. "
        "Удобно нажать **Authorize** в Swagger и получить токен без ручной подстановки JSON."
    ),
)
def login_oauth2_form(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> TokenResponse:
    return login_user(db, form_data.username, form_data.password)


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Текущий пользователь",
    description="Возвращает публичный профиль пользователя, извлечённого из JWT (без пароля).",
)
def read_current_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    return current_user


@router.patch(
    "/me",
    response_model=UserPublic,
    summary="Редактировать профиль",
    description=(
        "Обновляет имя, фамилию, отчество, телефон или фото профиля. "
        "Передавайте только те поля, которые нужно изменить — остальные останутся прежними. "
        "Чтобы **очистить** поле (например убрать телефон), явно передайте `null`. "
        "Для смены email используйте `PATCH /auth/me/email`, для пароля — `PATCH /auth/me/password`."
    ),
)
def update_my_profile(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> User:
    return update_profile(db, current_user, payload)


@router.patch(
    "/me/email",
    response_model=UserPublic,
    summary="Сменить email",
    description=(
        "Меняет email текущего пользователя. Требует подтверждения текущего пароля. "
        "Новый email должен быть уникальным в системе."
    ),
)
def update_my_email(
    payload: EmailChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> User:
    return change_email(db, current_user, payload)


@router.patch(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Сменить пароль",
    description="Меняет пароль. Требует передать текущий пароль (`current_password`) и новый (`new_password`, мин. 8 символов).",
)
def update_my_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    change_password(db, current_user, payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/me/location",
    response_model=UserPublic,
    summary="Обновить координаты (полная запись)",
    description=(
        "Сохраняет `lat` и `lng` в профиль пользователя и обновляет `location_updated_at`. "
        "Каждый вызов выполняет запись в БД — подходит для редких ручных обновлений."
    ),
)
def update_current_user_location(
    payload: UserLocationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> User:
    updated = update_user_location(
        db,
        current_user.id,
        lat=payload.lat,
        lng=payload.lng,
        coalesce_stationary_recent=False,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return updated


@router.put(
    "/me/location/live",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Потоковая геопозиция (204)",
    description=(
        "Предназначено для частых отправок координат (например каждые 3–5 с). Ответ **без тела** (204). "
        "Если координаты почти не изменились в пределах короткого окна времени, запись в БД может быть пропущена "
        "(снижение нагрузки при стоянии на месте)."
    ),
)
def push_location_live(
    payload: UserLocationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    updated = update_user_location(
        db,
        current_user.id,
        lat=payload.lat,
        lng=payload.lng,
        coalesce_stationary_recent=True,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
