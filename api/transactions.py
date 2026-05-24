from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_active_user
from models.user import User
from schemas.transaction import TransactionListOut
from services.payment_service import list_my_transactions

router = APIRouter(prefix="/transactions", tags=["Транзакции"])


@router.get(
    "/my",
    response_model=TransactionListOut,
    summary="Мои транзакции",
    description=(
        "История финансовых операций текущего пользователя (как плательщика и как получателя). "
        "Employer: видит свои списания при завершении заказов. "
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
