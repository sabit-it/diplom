"""
Интеграционные тесты для POST /transactions/deposit.
Проверяем пополнение баланса, структуру ответа, ограничения доступа и суммы.
"""
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

_SVC = "services.order_service"
_EXP = "services.offer_expiry"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def unique_email() -> str:
    return f"dep_{uuid.uuid4().hex[:12]}@example.com"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, role: str) -> tuple[dict, str]:
    payload = {
        "email": unique_email(),
        "password": "secret12345",
        "last_name": "Депозит",
        "first_name": "Тест",
        "patronymic": None,
        "role": role,
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 201
    return payload, resp.json()["access_token"]


def get_balance(client: TestClient, token: str) -> Decimal:
    return Decimal(client.get("/auth/me", headers=bearer(token)).json()["balance"])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# POST /transactions/deposit — базовое поведение
# ---------------------------------------------------------------------------

class TestDeposit:

    def test_returns_200(self, client):
        _, token = _register(client, "employer")
        resp = client.post("/transactions/deposit",
                           json={"amount": "500.00"}, headers=bearer(token))
        assert resp.status_code == 200

    def test_response_has_required_fields(self, client):
        _, token = _register(client, "employer")
        resp = client.post("/transactions/deposit",
                           json={"amount": "100.00"}, headers=bearer(token))
        body = resp.json()
        for field in ("transaction_id", "amount", "new_balance"):
            assert field in body, f"Missing field: {field}"

    def test_amount_in_response_matches_request(self, client):
        _, token = _register(client, "employer")
        resp = client.post("/transactions/deposit",
                           json={"amount": "750.50"}, headers=bearer(token))
        assert Decimal(resp.json()["amount"]) == Decimal("750.50")

    def test_new_balance_reflects_deposit(self, client):
        _, token = _register(client, "employer")
        client.post("/transactions/deposit",
                    json={"amount": "300.00"}, headers=bearer(token))
        resp = client.post("/transactions/deposit",
                           json={"amount": "200.00"}, headers=bearer(token))
        assert Decimal(resp.json()["new_balance"]) == Decimal("500.00")

    def test_balance_updated_in_profile(self, client):
        _, token = _register(client, "employer")
        client.post("/transactions/deposit",
                    json={"amount": "1000.00"}, headers=bearer(token))
        assert get_balance(client, token) == Decimal("1000.00")

    def test_multiple_deposits_accumulate(self, client):
        _, token = _register(client, "employer")
        client.post("/transactions/deposit", json={"amount": "100.00"}, headers=bearer(token))
        client.post("/transactions/deposit", json={"amount": "200.00"}, headers=bearer(token))
        client.post("/transactions/deposit", json={"amount": "50.00"},  headers=bearer(token))
        assert get_balance(client, token) == Decimal("350.00")

    def test_transaction_appears_in_history(self, client):
        _, token = _register(client, "employer")
        client.post("/transactions/deposit", json={"amount": "500.00"}, headers=bearer(token))
        txs = client.get("/transactions/my", headers=bearer(token)).json()
        assert txs["total"] >= 1
        deposit_txs = [t for t in txs["items"] if t["type"] == "deposit"]
        assert len(deposit_txs) >= 1

    def test_deposit_transaction_has_correct_type(self, client):
        _, token = _register(client, "employer")
        client.post("/transactions/deposit", json={"amount": "100.00"}, headers=bearer(token))
        txs = client.get("/transactions/my", headers=bearer(token)).json()
        tx = next(t for t in txs["items"] if t["type"] == "deposit")
        assert tx["type"] == "deposit"

    def test_deposit_transaction_order_id_is_null(self, client):
        _, token = _register(client, "employer")
        client.post("/transactions/deposit", json={"amount": "100.00"}, headers=bearer(token))
        txs = client.get("/transactions/my", headers=bearer(token)).json()
        tx = next(t for t in txs["items"] if t["type"] == "deposit")
        assert tx["order_id"] is None

    def test_deposit_commission_is_zero(self, client):
        _, token = _register(client, "employer")
        client.post("/transactions/deposit", json={"amount": "100.00"}, headers=bearer(token))
        txs = client.get("/transactions/my", headers=bearer(token)).json()
        tx = next(t for t in txs["items"] if t["type"] == "deposit")
        assert Decimal(tx["commission_amount"]) == Decimal("0.00")

    def test_transaction_id_is_valid_uuid(self, client):
        _, token = _register(client, "employer")
        resp = client.post("/transactions/deposit",
                           json={"amount": "100.00"}, headers=bearer(token))
        uuid.UUID(resp.json()["transaction_id"])  # не бросает — значит валидный


# ---------------------------------------------------------------------------
# Валидация суммы
# ---------------------------------------------------------------------------

class TestDepositValidation:

    def test_zero_amount_rejected(self, client):
        _, token = _register(client, "employer")
        resp = client.post("/transactions/deposit",
                           json={"amount": "0.00"}, headers=bearer(token))
        assert resp.status_code == 422

    def test_negative_amount_rejected(self, client):
        _, token = _register(client, "employer")
        resp = client.post("/transactions/deposit",
                           json={"amount": "-100.00"}, headers=bearer(token))
        assert resp.status_code == 422

    def test_above_max_rejected(self, client):
        _, token = _register(client, "employer")
        resp = client.post("/transactions/deposit",
                           json={"amount": "1000001.00"}, headers=bearer(token))
        assert resp.status_code == 422

    def test_max_amount_accepted(self, client):
        _, token = _register(client, "employer")
        resp = client.post("/transactions/deposit",
                           json={"amount": "1000000.00"}, headers=bearer(token))
        assert resp.status_code == 200

    def test_min_amount_accepted(self, client):
        _, token = _register(client, "employer")
        resp = client.post("/transactions/deposit",
                           json={"amount": "0.01"}, headers=bearer(token))
        assert resp.status_code == 200

    def test_missing_amount_rejected(self, client):
        _, token = _register(client, "employer")
        resp = client.post("/transactions/deposit", json={}, headers=bearer(token))
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Ограничения доступа
# ---------------------------------------------------------------------------

class TestDepositAccess:

    def test_worker_forbidden(self, client):
        _, token = _register(client, "worker")
        resp = client.post("/transactions/deposit",
                           json={"amount": "500.00"}, headers=bearer(token))
        assert resp.status_code == 403

    def test_unauthenticated_rejected(self, client):
        resp = client.post("/transactions/deposit", json={"amount": "500.00"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Интеграция с order_settlement — оба типа в истории
# ---------------------------------------------------------------------------

class TestDepositWithOrderHistory:

    def test_deposit_and_settlement_both_visible(self, client, db):
        from decimal import Decimal as D
        from models.profession import Profession
        from models.worker_profile import WorkerProfile

        p = Profession(
            id=30500,
            name=f"ДепТест_{uuid.uuid4().hex[:6]}",
            hourly_rate=D("500.00"),
            rate_unit="hour",
            is_active=True,
        )
        db.add(p)
        db.commit()

        _, emp_token = _register(client, "employer")
        _, wrk_token = _register(client, "worker")

        wrk_id = uuid.UUID(client.get("/auth/me", headers=bearer(wrk_token)).json()["id"])
        wp = WorkerProfile(
            user_id=wrk_id,
            profession_id=p.id,
            is_online=True,
            current_lat=D("55.752000"),
            current_lng=D("37.619000"),
        )
        db.add(wp)
        db.commit()

        # Пополнение
        client.post("/transactions/deposit", json={"amount": "2000.00"}, headers=bearer(emp_token))

        # Создание и завершение заказа
        cr = client.post("/orders/", json={
            "profession_id": p.id,
            "title": "Тест депозит+заказ",
            "hours": 2,
            "hourly_rate": "500.00",
            "address": "Москва",
            "lat": "55.751244",
            "lng": "37.618423",
        }, headers=bearer(emp_token))
        order_id = cr.json()["order"]["id"]
        offer_id = cr.json()["active_offer_id"]
        client.post(f"/orders/offers/{offer_id}/respond", json={"accept": True}, headers=bearer(wrk_token))
        client.patch(f"/orders/{order_id}/complete", headers=bearer(emp_token))

        txs = client.get("/transactions/my", headers=bearer(emp_token)).json()
        types = {t["type"] for t in txs["items"]}
        assert "deposit" in types
        assert "order_settlement" in types

    def test_deposit_allows_negative_balance_recovery(self, client, db):
        """После списания по заказу депозит возвращает баланс в плюс."""
        from decimal import Decimal as D
        from models.profession import Profession
        from models.worker_profile import WorkerProfile

        p = Profession(
            id=30501,
            name=f"ДепТест2_{uuid.uuid4().hex[:6]}",
            hourly_rate=D("500.00"),
            rate_unit="hour",
            is_active=True,
        )
        db.add(p)
        db.commit()

        _, emp_token = _register(client, "employer")
        _, wrk_token = _register(client, "worker")

        wrk_id = uuid.UUID(client.get("/auth/me", headers=bearer(wrk_token)).json()["id"])
        wp = WorkerProfile(
            user_id=wrk_id,
            profession_id=p.id,
            is_online=True,
            current_lat=D("55.752000"),
            current_lng=D("37.619000"),
        )
        db.add(wp)
        db.commit()

        # Заказ на 1000 ₽ — баланс уйдёт в минус
        cr = client.post("/orders/", json={
            "profession_id": p.id,
            "title": "Тест минус",
            "hours": 2,
            "hourly_rate": "500.00",
            "address": "Москва",
            "lat": "55.751244",
            "lng": "37.618423",
        }, headers=bearer(emp_token))
        order_id = cr.json()["order"]["id"]
        offer_id = cr.json()["active_offer_id"]
        client.post(f"/orders/offers/{offer_id}/respond", json={"accept": True}, headers=bearer(wrk_token))
        client.patch(f"/orders/{order_id}/complete", headers=bearer(emp_token))

        balance_after_order = get_balance(client, emp_token)
        assert balance_after_order < 0

        # Депозит покрывает долг
        client.post("/transactions/deposit",
                    json={"amount": "1500.00"}, headers=bearer(emp_token))
        balance_final = get_balance(client, emp_token)
        assert balance_final > 0
        assert balance_final == balance_after_order + Decimal("1500.00")
