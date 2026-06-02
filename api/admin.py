import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import require_admin
from models.order import Order
from models.profession import Profession
from models.review import Review
from models.transaction import Transaction
from models.user import User
from schemas.admin import (
    AdminBlockRequest,
    AdminOrderListOut,
    AdminOrderOut,
    AdminStatsOut,
    AdminTransactionListOut,
    AdminTransactionOut,
    AdminUserListOut,
    AdminUserOut,
    ProfessionCreate,
    ProfessionUpdate,
)
from schemas.profession import ProfessionOut
from schemas.review import ReviewOut

router = APIRouter(prefix="/admin", tags=["Админ"])


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users", response_model=AdminUserListOut, summary="Список пользователей")
def list_users(
    role: str | None = Query(default=None, description="Фильтр по роли: employer, worker."),
    is_blocked: bool | None = Query(default=None, description="Фильтр по блокировке."),
    q: str | None = Query(default=None, description="Поиск по email, имени или фамилии."),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> AdminUserListOut:
    query = select(User)
    if role is not None:
        query = query.where(User.role == role)
    if is_blocked is not None:
        query = query.where(User.is_blocked == is_blocked)
    if q:
        query = query.where(or_(
            User.email.ilike(f"%{q}%"),
            User.first_name.ilike(f"%{q}%"),
            User.last_name.ilike(f"%{q}%"),
        ))
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    users = list(db.execute(query.order_by(User.created_at.desc()).offset(offset).limit(limit)).scalars())
    return AdminUserListOut(
        items=[AdminUserOut.model_validate(u) for u in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}", response_model=AdminUserOut, summary="Пользователь по ID")
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> AdminUserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return AdminUserOut.model_validate(user)


@router.patch(
    "/users/{user_id}/block",
    response_model=AdminUserOut,
    summary="Заблокировать / разблокировать пользователя",
)
def block_user(
    user_id: uuid.UUID,
    payload: AdminBlockRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя заблокировать себя.")
    user.is_blocked = payload.is_blocked
    db.commit()
    db.refresh(user)
    return AdminUserOut.model_validate(user)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Деактивировать пользователя",
    description="Устанавливает `is_active=False`. Данные сохраняются.",
)
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя деактивировать себя.")
    user.is_active = False
    db.commit()


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

@router.get("/orders", response_model=AdminOrderListOut, summary="Все заказы")
def list_orders(
    order_status: str | None = Query(default=None, description="Фильтр по статусу заказа."),
    employer_id: uuid.UUID | None = Query(default=None, description="Фильтр по заказчику."),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> AdminOrderListOut:
    query = select(Order)
    if order_status is not None:
        query = query.where(Order.status == order_status)
    if employer_id is not None:
        query = query.where(Order.employer_id == employer_id)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    orders = list(db.execute(query.order_by(Order.created_at.desc()).offset(offset).limit(limit)).scalars())
    return AdminOrderListOut(
        items=[AdminOrderOut.model_validate(o) for o in orders],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/orders/{order_id}", response_model=AdminOrderOut, summary="Заказ по ID")
def get_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> AdminOrderOut:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return AdminOrderOut.model_validate(order)


# ---------------------------------------------------------------------------
# Professions
# ---------------------------------------------------------------------------

@router.get("/professions", response_model=list[ProfessionOut], summary="Все профессии")
def list_all_professions(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[ProfessionOut]:
    rows = db.execute(select(Profession).order_by(Profession.id)).scalars().all()
    return [ProfessionOut.model_validate(r) for r in rows]


@router.post(
    "/professions",
    response_model=ProfessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать профессию",
)
def create_profession(
    payload: ProfessionCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ProfessionOut:
    if payload.id is not None:
        if db.get(Profession, payload.id) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Профессия с таким ID уже существует.")
        next_id = payload.id
    else:
        max_id = db.execute(select(func.max(Profession.id))).scalar_one()
        next_id = (max_id or 0) + 1
    profession = Profession(
        id=next_id,
        name=payload.name,
        hourly_rate=payload.hourly_rate,
        rate_unit=payload.rate_unit.value,
        is_active=True,
    )
    db.add(profession)
    db.commit()
    db.refresh(profession)
    return ProfessionOut.model_validate(profession)


@router.patch("/professions/{profession_id}", response_model=ProfessionOut, summary="Обновить профессию")
def update_profession(
    profession_id: int,
    payload: ProfessionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ProfessionOut:
    profession = db.get(Profession, profession_id)
    if profession is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profession not found")
    if payload.name is not None:
        profession.name = payload.name
    if payload.hourly_rate is not None:
        profession.hourly_rate = payload.hourly_rate
    if payload.rate_unit is not None:
        profession.rate_unit = payload.rate_unit.value
    if payload.is_active is not None:
        profession.is_active = payload.is_active
    db.commit()
    db.refresh(profession)
    return ProfessionOut.model_validate(profession)


@router.delete(
    "/professions/{profession_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Деактивировать профессию",
    description="Устанавливает `is_active=False`. Существующие заказы не затрагиваются.",
)
def deactivate_profession(
    profession_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    profession = db.get(Profession, profession_id)
    if profession is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profession not found")
    profession.is_active = False
    db.commit()


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

@router.get("/transactions", response_model=AdminTransactionListOut, summary="Все транзакции")
def list_transactions(
    tx_type: str | None = Query(default=None, description="Фильтр по типу: deposit, withdrawal, order_settlement."),
    user_id: uuid.UUID | None = Query(default=None, description="Фильтр по участнику (payer или receiver)."),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> AdminTransactionListOut:
    query = select(Transaction)
    if tx_type is not None:
        query = query.where(Transaction.type == tx_type)
    if user_id is not None:
        query = query.where(or_(Transaction.payer_id == user_id, Transaction.receiver_id == user_id))
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    txs = list(db.execute(query.order_by(Transaction.created_at.desc()).offset(offset).limit(limit)).scalars())
    return AdminTransactionListOut(
        items=[AdminTransactionOut.model_validate(t) for t in txs],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=AdminStatsOut, summary="Статистика платформы")
def get_stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> AdminStatsOut:
    from models.user import User as U
    from models.order import Order as O
    from models.transaction import Transaction as T

    total_users = db.execute(select(func.count()).select_from(select(U).subquery())).scalar_one()
    total_employers = db.execute(select(func.count()).where(U.role == "employer")).scalar_one()
    total_workers = db.execute(select(func.count()).where(U.role == "worker")).scalar_one()
    total_orders = db.execute(select(func.count()).select_from(select(O).subquery())).scalar_one()
    completed_orders = db.execute(select(func.count()).where(O.status == "completed")).scalar_one()
    cancelled_orders = db.execute(select(func.count()).where(O.status == "cancelled")).scalar_one()

    revenue_row = db.execute(
        select(func.coalesce(func.sum(T.commission_amount), 0)).where(T.type == "order_settlement")
    ).scalar_one()
    volume_row = db.execute(
        select(func.coalesce(func.sum(T.amount), 0))
    ).scalar_one()

    from decimal import Decimal
    return AdminStatsOut(
        total_users=total_users,
        total_employers=total_employers,
        total_workers=total_workers,
        total_orders=total_orders,
        completed_orders=completed_orders,
        cancelled_orders=cancelled_orders,
        total_platform_revenue=Decimal(str(revenue_row)),
        total_volume=Decimal(str(volume_row)),
    )


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

@router.get("/reviews", summary="Все отзывы")
def list_all_reviews(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    q = select(Review).order_by(Review.created_at.desc())
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(q.offset(offset).limit(limit)).scalars().all()
    return {"items": [ReviewOut.model_validate(r) for r in rows], "total": total}


@router.delete(
    "/reviews/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить отзыв",
)
def delete_review(
    review_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    review = db.get(Review, review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    db.delete(review)
    db.commit()
