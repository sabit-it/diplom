"""
Интеграционные тесты для транзакций и балансов (settle_order при complete).
"""
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.profession import Profession
from models.worker_profile import WorkerProfile

_SVC = "services.order_service"
_EXP = "services.offer_expiry"

ORDER_LAT = "55.751244"
ORDER_LNG = "37.618423"
WORKER_LAT = "55.752000"
WORKER_LNG = "37.619000"


def unique_email() -> str:
    return f"tx_{uuid.uuid4().hex[:12]}@example.com"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, role: str) -> tuple[dict, str]:
    payload = {
        "email": unique_email(),
        "password": "secret12345",
        "last_name": "Транзак",
        "first_name": "Тест",
        "patronymic": None,
        "role": role,
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 201
    return payload, resp.json()["access_token"]


def get_user_id(client: TestClient, token: str) -> uuid.UUID:
    return uuid.UUID(client.get("/auth/me", headers=bearer(token)).json()["id"])


def get_balance(client: TestClient, token: str) -> Decimal:
    return Decimal(client.get("/auth/me", headers=bearer(token)).json()["balance"])


def make_worker_profile(db: Session, user_id: uuid.UUID, profession_id: int) -> WorkerProfile:
    wp = WorkerProfile(
        user_id=user_id,
        profession_id=profession_id,
        is_online=True,
        current_lat=Decimal(WORKER_LAT),
        current_lng=Decimal(WORKER_LNG),
    )
    db.add(wp)
    db.commit()
    db.refresh(wp)
    return wp


def create_and_complete_order(client: TestClient, db: Session, profession_id: int):
    """Создаёт заказ, принимает, завершает. Возвращает (order_id, emp_token, wrk_token, total_price)."""
    _, emp_token = _register(client, "employer")
    _, wrk_token = _register(client, "worker")
    make_worker_profile(db, get_user_id(client, wrk_token), profession_id)

    order_payload = {
        "profession_id": profession_id,
        "title": "Тест оплаты",
        "hours": 2,
        "hourly_rate": "500.00",
        "address": "Москва",
        "lat": ORDER_LAT,
        "lng": ORDER_LNG,
    }
    cr = client.post("/orders/", json=order_payload, headers=bearer(emp_token))
    order_id = cr.json()["order"]["id"]
    offer_id = cr.json()["active_offer_id"]
    total_price = Decimal(cr.json()["order"]["total_price"])

    client.post(f"/orders/offers/{offer_id}/respond", json={"accept": True}, headers=bearer(wrk_token))
    client.patch(f"/orders/{order_id}/complete", headers=bearer(emp_token))

    return order_id, emp_token, wrk_token, total_price


@pytest.fixture(autouse=True)
def _no_emails():
    with (
        patch(f"{_SVC}.notify_worker_new_offer"),
        patch(f"{_SVC}.notify_employer_worker_accepted"),
        patch(f"{_SVC}.notify_employer_worker_declined"),
        patch(f"{_SVC}.notify_no_workers"),
        patch(f"{_SVC}.notify_order_completed"),
        patch(f"{_SVC}.notify_worker_order_cancelled"),
        patch(f"{_EXP}.notify_employer_offer_timed_out"),
        patch(f"{_EXP}.notify_worker_new_offer"),
    ):
        yield


@pytest.fixture()
def profession(db: Session) -> int:
    p = Profession(
        id=30001,
        name=f"ТрТест_{uuid.uuid4().hex[:8]}",
        hourly_rate=Decimal("500.00"),
        rate_unit="hour",
        is_active=True,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


class TestBalances:

    def test_employer_balance_decreases_on_complete(self, client, db, profession):
        _, emp_token, _, total = create_and_complete_order(client, db, profession)
        balance = get_balance(client, emp_token)
        assert balance == -total

    def test_worker_balance_increases_on_complete(self, client, db, profession):
        _, _, wrk_token, total = create_and_complete_order(client, db, profession)
        balance = get_balance(client, wrk_token)
        commission = (total * Decimal("10") / Decimal("100")).quantize(Decimal("0.01"))
        expected = total - commission
        assert balance == expected

    def test_initial_balance_is_zero(self, client, db):
        _, token = _register(client, "employer")
        balance = get_balance(client, token)
        assert balance == Decimal("0.00")


class TestTransactionsList:

    def test_employer_sees_transaction(self, client, db, profession):
        order_id, emp_token, _, _ = create_and_complete_order(client, db, profession)
        resp = client.get("/transactions/my", headers=bearer(emp_token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        tx = data["items"][0]
        assert tx["order_id"] == order_id

    def test_worker_sees_transaction(self, client, db, profession):
        order_id, _, wrk_token, _ = create_and_complete_order(client, db, profession)
        resp = client.get("/transactions/my", headers=bearer(wrk_token))
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_transaction_fields(self, client, db, profession):
        _, emp_token, _, total = create_and_complete_order(client, db, profession)
        resp = client.get("/transactions/my", headers=bearer(emp_token))
        tx = resp.json()["items"][0]
        for field in ("id", "order_id", "payer_id", "receiver_id",
                      "amount", "commission_amount", "worker_amount", "status", "created_at"):
            assert field in tx, f"Missing field: {field}"

    def test_commission_and_worker_amount(self, client, db, profession):
        _, emp_token, _, total = create_and_complete_order(client, db, profession)
        tx = client.get("/transactions/my", headers=bearer(emp_token)).json()["items"][0]
        amount = Decimal(tx["amount"])
        commission = Decimal(tx["commission_amount"])
        worker_amount = Decimal(tx["worker_amount"])
        assert amount == total
        assert worker_amount == amount - commission
        expected_commission = (amount * Decimal("10") / Decimal("100")).quantize(Decimal("0.01"))
        assert commission == expected_commission

    def test_empty_list_for_new_user(self, client, db):
        _, token = _register(client, "employer")
        resp = client.get("/transactions/my", headers=bearer(token))
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []

    def test_unauthenticated_rejected(self, client, db):
        resp = client.get("/transactions/my")
        assert resp.status_code == 401

    def test_pagination(self, client, db, profession):
        _, emp_token, _, _ = create_and_complete_order(client, db, profession)
        resp = client.get("/transactions/my", params={"limit": 1, "offset": 0}, headers=bearer(emp_token))
        assert resp.status_code == 200
        assert len(resp.json()["items"]) <= 1
