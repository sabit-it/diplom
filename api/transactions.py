from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_active_user
from models.user import User
from schemas.transaction import DepositOut, DepositRequest, TransactionListOut, TransactionSummaryOut, WithdrawOut, WithdrawRequest
from services.payment_service import deposit_balance, get_my_summary, list_my_transactions, withdraw_balance

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
    return deposit_balance(db, user, payload.amount, payload.card_number)


@router.post(
    "/withdraw",
    response_model=WithdrawOut,
    status_code=status.HTTP_200_OK,
    summary="Вывести средства",
    description=(
        "Только для **worker**. Выводит указанную сумму с внутреннего баланса исполнителя на банковскую карту. "
        "Данные карты проходят валидацию (номер, срок действия, CVV), но не сохраняются в БД. "
        "Ограничение суммы: от 0.01 до 1 000 000 ₽. Баланс не может уйти ниже нуля."
    ),
)
def withdraw(
    payload: WithdrawRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> WithdrawOut:
    return withdraw_balance(db, user, payload.amount, payload.card_number)


@router.get(
    "/my",
    response_model=TransactionListOut,
    summary="Мои транзакции",
    description=(
        "История финансовых операций текущего пользователя. "
        "Фильтр `type`: `deposit` — пополнения, `withdrawal` — выводы, `order_settlement` — расчёты по заказам. "
        "Без фильтра — все операции. Сортировка: новые первые."
    ),
)
def get_my_transactions(
    limit: int = Query(default=20, ge=1, le=100, description="Кол-во записей на странице."),
    offset: int = Query(default=0, ge=0, description="Смещение."),
    type: str | None = Query(default=None, description="Фильтр по типу: deposit, withdrawal, order_settlement."),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> TransactionListOut:
    return list_my_transactions(db, user, limit=limit, offset=offset, tx_type=type)


@router.get(
    "/summary",
    response_model=TransactionSummaryOut,
    summary="Сводка по транзакциям",
    description=(
        "Агрегированные данные по финансам текущего пользователя: "
        "текущий баланс, итого пополнено, выведено, заработано и потрачено за всё время."
    ),
)
def get_summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> TransactionSummaryOut:
    return get_my_summary(db, user)
