from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_active_user
from models.user import User
from schemas.review import ReviewCreate, ReviewOut
from repositories.review_repository import list_reviews_for_recipient
from services.review_service import (
    create_review_for_order,
    list_my_given_reviews,
    list_my_received_reviews,
    list_order_reviews_for_participant,
)

router = APIRouter(prefix="/reviews", tags=["Отзывы"])


@router.post(
    "/",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
    summary="Оставить отзыв по заказу",
    description=(
        "Доступно участникам заказа (**заказчик** или **исполнитель**) после перевода заказа в статус **completed** "
        "(см. `PATCH /orders/{order_id}/complete`). Оценивается **второй** участник сделки; один автор — не более "
        "одного отзыва на заказ. Если оцениваемый — исполнитель (`worker`), пересчитываются `rating_avg` и "
        "`reviews_count` в `worker_profiles` по всем отзывам, где он указан как получатель."
    ),
)
def post_review(
    payload: ReviewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> ReviewOut:
    return create_review_for_order(db, user, payload)


@router.get(
    "/received",
    response_model=list[ReviewOut],
    summary="Отзывы обо мне",
    description="Список отзывов, где текущий пользователь указан как **recipient** (новые сверху).",
)
def get_reviews_about_me(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[ReviewOut]:
    return list_my_received_reviews(db, user)


@router.get(
    "/given",
    response_model=list[ReviewOut],
    summary="Мои отзывы",
    description="Список отзывов, которые оставил текущий пользователь (**author**).",
)
def get_my_reviews(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[ReviewOut]:
    return list_my_given_reviews(db, user)


@router.get(
    "/for-user/{user_id}",
    response_model=list[ReviewOut],
    summary="Отзывы о пользователе по user_id",
)
def get_reviews_for_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> list[ReviewOut]:
    rows = list_reviews_for_recipient(db, user_id)
    return [ReviewOut.model_validate(r) for r in rows]


@router.get(
    "/by-order/{order_id}",
    response_model=list[ReviewOut],
    summary="Отзывы по конкретному заказу",
    description="Только для участников заказа: все отзывы, привязанные к этому `order_id`.",
)
def get_reviews_for_order(
    order_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[ReviewOut]:
    return list_order_reviews_for_participant(db, user, order_id)
