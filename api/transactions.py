from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_active_user
from models.user import User
from schemas.transaction import DepositOut, DepositRequest, TransactionListOut
from services.payment_service import deposit_balance, list_my_transactions

router = APIRouter(prefix="/transactions", tags=["Транзакции"])


@router.post(
    "/deposit",
    response_model=DepositOut,
    status_code=status.HTTP_200_OK,
    summary="Пополнить баланс",
    description=(
        "Только для **employer**. Зачисляет указанную сумму на внутренний баланс заказчика. "
        "Создаётся транзакция типа `deposit` (без привязки к заказу). "
        "Баланс используется для оплаты заказов при их завершении (`PATCH /orders/{id}/complete`). "
        "Ограничение суммы: от 0.01 до 1 000 000 ₽ за операцию."
    ),
)
def deposit(
    payload: DepositRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> DepositOut:
    return deposit_balance(db, user, payload.amount)


@router.get(
    "/my",
    response_model=TransactionListOut,
    summary="Мои транзакции",
    description=(
        "История финансовых операций текущего пользователя (как плательщика и как получателя). "
        "Employer: видит пополнения (`deposit`) и списания (`order_settlement`) при завершении заказов. "
        "Worker: видит свои начисления (уже за вычетом комиссии платформы). "
        "Сортировка: новые первые. Пагинация через `limit` и `offset`."
    ),
)
def get_my_transactions(
    limit: int = Query(default=20, ge=1, le=100, description="Кол-во записей на странице."),
    offset: int = Query(default=0, ge=0, description="Смещение."),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> TransactionListOut:
    return list_my_transactions(db, user, limit=limit, offset=offset)
