"""
Интеграционные тесты для /admin/* эндпоинтов.
"""
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.profession import Profession
from models.review import Review
from models.user import User

_SVC = "services.order_service"
_EXP = "services.offer_expiry"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def unique_email() -> str:
    return f"adm_{uuid.uuid4().hex[:12]}@example.com"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, role: str) -> tuple[str, str]:
    email = unique_email()
    resp = client.post("/auth/register", json={
        "email": email,
        "password": "secret12345",
        "last_name": "Тест",
        "first_name": "Тест",
        "patronymic": None,
        "role": role,
    })
    assert resp.status_code == 201
    return email, resp.json()["access_token"]


def _make_admin(db: Session, email: str) -> None:
    user = db.execute(__import__("sqlalchemy").select(User).where(User.email == email)).scalar_one()
    user.is_admin = True
    db.flush()


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


@pytest.fixture()
def admin(client: TestClient, db: Session):
    email, token = _register(client, "employer")
    _make_admin(db, email)
    return token


@pytest.fixture()
def employer(client: TestClient):
    _, token = _register(client, "employer")
    return token


@pytest.fixture()
def worker(client: TestClient):
    _, token = _register(client, "worker")
    return token


# ---------------------------------------------------------------------------
# Доступ — 403 для не-администраторов
# ---------------------------------------------------------------------------

class TestAdminAccess:

    def test_employer_cannot_access_users(self, client, employer):
        assert client.get("/admin/users", headers=bearer(employer)).status_code == 403

    def test_worker_cannot_access_users(self, client, worker):
        assert client.get("/admin/users", headers=bearer(worker)).status_code == 403

    def test_unauthenticated_rejected(self, client):
        assert client.get("/admin/users").status_code == 401

    def test_employer_cannot_access_stats(self, client, employer):
        assert client.get("/admin/stats", headers=bearer(employer)).status_code == 403

    def test_employer_cannot_block_user(self, client, employer):
        fake_id = uuid.uuid4()
        resp = client.patch(f"/admin/users/{fake_id}/block",
                            json={"is_blocked": True}, headers=bearer(employer))
        assert resp.status_code == 403

    def test_employer_cannot_create_profession(self, client, employer):
        resp = client.post("/admin/professions",
                           json={"id": 999, "name": "X", "hourly_rate": "100.00"},
                           headers=bearer(employer))
        assert resp.status_code == 403

    def test_employer_cannot_access_transactions(self, client, employer):
        assert client.get("/admin/transactions", headers=bearer(employer)).status_code == 403


# ---------------------------------------------------------------------------
# Пользователи
# ---------------------------------------------------------------------------

class TestAdminUsers:

    def test_list_returns_200(self, client, admin):
        resp = client.get("/admin/users", headers=bearer(admin))
        assert resp.status_code == 200

    def test_list_has_pagination_fields(self, client, admin):
        body = client.get("/admin/users", headers=bearer(admin)).json()
        assert "items" in body and "total" in body

    def test_list_filter_by_role(self, client, admin, worker):
        body = client.get("/admin/users?role=worker", headers=bearer(admin)).json()
        assert all(u["role"] == "worker" for u in body["items"])

    def test_list_filter_by_blocked(self, client, admin, db):
        email2, _ = _register(client, "employer")
        user = db.execute(__import__("sqlalchemy").select(User).where(User.email == email2)).scalar_one()
        user.is_blocked = True
        db.flush()
        body = client.get("/admin/users?is_blocked=true", headers=bearer(admin)).json()
        assert all(u["is_blocked"] for u in body["items"])

    def test_list_search_by_email(self, client, admin):
        email, _ = _register(client, "employer")
        body = client.get(f"/admin/users?q={email[:10]}", headers=bearer(admin)).json()
        assert any(u["email"] == email for u in body["items"])

    def test_get_user_returns_200(self, client, admin):
        body = client.get("/admin/users", headers=bearer(admin)).json()
        user_id = body["items"][0]["id"]
        resp = client.get(f"/admin/users/{user_id}", headers=bearer(admin))
        assert resp.status_code == 200

    def test_get_user_not_found(self, client, admin):
        resp = client.get(f"/admin/users/{uuid.uuid4()}", headers=bearer(admin))
        assert resp.status_code == 404

    def test_block_user(self, client, admin, employer, db):
        emp_id = client.get("/auth/me", headers=bearer(employer)).json()["id"]
        resp = client.patch(f"/admin/users/{emp_id}/block",
                            json={"is_blocked": True}, headers=bearer(admin))
        assert resp.status_code == 200
        assert resp.json()["is_blocked"] is True

    def test_unblock_user(self, client, admin, employer):
        emp_id = client.get("/auth/me", headers=bearer(employer)).json()["id"]
        client.patch(f"/admin/users/{emp_id}/block",
                     json={"is_blocked": True}, headers=bearer(admin))
        resp = client.patch(f"/admin/users/{emp_id}/block",
                            json={"is_blocked": False}, headers=bearer(admin))
        assert resp.json()["is_blocked"] is False

    def test_blocked_user_cannot_login(self, client, admin, db):
        email, token = _register(client, "employer")
        user = db.execute(__import__("sqlalchemy").select(User).where(User.email == email)).scalar_one()
        user.is_blocked = True
        db.flush()
        resp = client.get("/auth/me", headers=bearer(token))
        assert resp.status_code == 403

    def test_cannot_block_yourself(self, client, admin, db):
        admin_id = client.get("/auth/me", headers=bearer(admin)).json()["id"]
        resp = client.patch(f"/admin/users/{admin_id}/block",
                            json={"is_blocked": True}, headers=bearer(admin))
        assert resp.status_code == 400

    def test_delete_user_deactivates(self, client, admin, employer):
        emp_id = client.get("/auth/me", headers=bearer(employer)).json()["id"]
        resp = client.delete(f"/admin/users/{emp_id}", headers=bearer(admin))
        assert resp.status_code == 204
        body = client.get(f"/admin/users/{emp_id}", headers=bearer(admin)).json()
        assert body["is_active"] is False

    def test_cannot_delete_yourself(self, client, admin):
        admin_id = client.get("/auth/me", headers=bearer(admin)).json()["id"]
        resp = client.delete(f"/admin/users/{admin_id}", headers=bearer(admin))
        assert resp.status_code == 400

    def test_user_has_is_admin_field(self, client, admin):
        body = client.get("/admin/users", headers=bearer(admin)).json()
        assert "is_admin" in body["items"][0]


# ---------------------------------------------------------------------------
# Заказы
# ---------------------------------------------------------------------------

class TestAdminOrders:

    def test_list_returns_200(self, client, admin):
        resp = client.get("/admin/orders", headers=bearer(admin))
        assert resp.status_code == 200

    def test_list_has_pagination_fields(self, client, admin):
        body = client.get("/admin/orders", headers=bearer(admin)).json()
        assert "items" in body and "total" in body

    def test_filter_by_status(self, client, admin):
        body = client.get("/admin/orders?order_status=completed", headers=bearer(admin)).json()
        assert all(o["status"] == "completed" for o in body["items"])

    def test_filter_by_employer(self, client, admin, employer):
        emp_id = client.get("/auth/me", headers=bearer(employer)).json()["id"]
        body = client.get(f"/admin/orders?employer_id={emp_id}", headers=bearer(admin)).json()
        assert all(o["employer_id"] == emp_id for o in body["items"])

    def test_get_order_not_found(self, client, admin):
        resp = client.get(f"/admin/orders/{uuid.uuid4()}", headers=bearer(admin))
        assert resp.status_code == 404

    def test_order_has_required_fields(self, client, admin, db):
        p = Profession(id=30001, name=f"АдмТест_{uuid.uuid4().hex[:6]}",
                       hourly_rate=Decimal("100.00"), rate_unit="hour", is_active=True)
        db.add(p)
        db.flush()
        _, emp_token = _register(client, "employer")
        client.post("/transactions/deposit", json={
            "amount": "1000.00", "card_number": "4111111111111111",
            "card_holder": "TEST USER", "expiry_month": 12, "expiry_year": 2027, "cvv": "123",
        }, headers=bearer(emp_token))
        cr = client.post("/orders/", json={
            "profession_id": p.id, "title": "Тест", "hours": 1,
            "hourly_rate": "100.00", "address": "Москва",
            "lat": "55.751244", "lng": "37.618423",
        }, headers=bearer(emp_token))
        order_id = cr.json()["order"]["id"]
        body = client.get(f"/admin/orders/{order_id}", headers=bearer(admin)).json()
        for field in ("id", "employer_id", "status", "total_price", "created_at"):
            assert field in body


# ---------------------------------------------------------------------------
# Профессии
# ---------------------------------------------------------------------------

class TestAdminProfessions:

    def test_create_profession(self, client, admin):
        resp = client.post("/admin/professions", json={
            "id": 30100, "name": f"Тест_{uuid.uuid4().hex[:6]}",
            "hourly_rate": "250.00", "rate_unit": "hour",
        }, headers=bearer(admin))
        assert resp.status_code == 201
        assert resp.json()["is_active"] is True

    def test_create_duplicate_id_rejected(self, client, admin):
        payload = {"id": 30101, "name": f"Уник_{uuid.uuid4().hex[:6]}", "hourly_rate": "100.00"}
        client.post("/admin/professions", json=payload, headers=bearer(admin))
        resp = client.post("/admin/professions",
                           json={**payload, "name": "Другое"}, headers=bearer(admin))
        assert resp.status_code == 409

    def test_update_profession_name(self, client, admin, db):
        p = Profession(id=30102, name=f"До_{uuid.uuid4().hex[:6]}",
                       hourly_rate=Decimal("100.00"), rate_unit="hour", is_active=True)
        db.add(p)
        db.flush()
        new_name = f"После_{uuid.uuid4().hex[:6]}"
        resp = client.patch(f"/admin/professions/{p.id}",
                            json={"name": new_name}, headers=bearer(admin))
        assert resp.status_code == 200
        assert resp.json()["name"] == new_name

    def test_update_profession_rate(self, client, admin, db):
        p = Profession(id=30103, name=f"Рейт_{uuid.uuid4().hex[:6]}",
                       hourly_rate=Decimal("100.00"), rate_unit="hour", is_active=True)
        db.add(p)
        db.flush()
        resp = client.patch(f"/admin/professions/{p.id}",
                            json={"hourly_rate": "500.00"}, headers=bearer(admin))
        assert Decimal(resp.json()["hourly_rate"]) == Decimal("500.00")

    def test_deactivate_profession(self, client, admin, db):
        p = Profession(id=30104, name=f"Деакт_{uuid.uuid4().hex[:6]}",
                       hourly_rate=Decimal("100.00"), rate_unit="hour", is_active=True)
        db.add(p)
        db.flush()
        resp = client.delete(f"/admin/professions/{p.id}", headers=bearer(admin))
        assert resp.status_code == 204
        check = client.patch(f"/admin/professions/{p.id}",
                             json={}, headers=bearer(admin)).json()
        assert check["is_active"] is False

    def test_update_not_found(self, client, admin):
        resp = client.patch("/admin/professions/99999", json={"name": "X"}, headers=bearer(admin))
        assert resp.status_code == 404

    def test_deactivated_profession_unavailable_in_catalog(self, client, admin, db):
        p = Profession(id=30105, name=f"Скрыт_{uuid.uuid4().hex[:6]}",
                       hourly_rate=Decimal("100.00"), rate_unit="hour", is_active=True)
        db.add(p)
        db.flush()
        client.delete(f"/admin/professions/{p.id}", headers=bearer(admin))
        resp = client.get(f"/professions/{p.id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Транзакции
# ---------------------------------------------------------------------------

class TestAdminTransactions:

    def test_list_returns_200(self, client, admin):
        resp = client.get("/admin/transactions", headers=bearer(admin))
        assert resp.status_code == 200

    def test_has_pagination_fields(self, client, admin):
        body = client.get("/admin/transactions", headers=bearer(admin)).json()
        assert "items" in body and "total" in body

    def test_filter_by_type(self, client, admin, employer):
        client.post("/transactions/deposit", json={
            "amount": "100.00", "card_number": "4111111111111111",
            "card_holder": "TEST", "expiry_month": 12, "expiry_year": 2027, "cvv": "123",
        }, headers=bearer(employer))
        body = client.get("/admin/transactions?tx_type=deposit", headers=bearer(admin)).json()
        assert all(t["type"] == "deposit" for t in body["items"])

    def test_filter_by_user_id(self, client, admin, employer):
        emp_id = client.get("/auth/me", headers=bearer(employer)).json()["id"]
        body = client.get(f"/admin/transactions?user_id={emp_id}", headers=bearer(admin)).json()
        for t in body["items"]:
            assert t["payer_id"] == emp_id or t["receiver_id"] == emp_id

    def test_transaction_has_required_fields(self, client, admin, employer):
        client.post("/transactions/deposit", json={
            "amount": "50.00", "card_number": "4111111111111111",
            "card_holder": "TEST", "expiry_month": 12, "expiry_year": 2027, "cvv": "123",
        }, headers=bearer(employer))
        body = client.get("/admin/transactions?tx_type=deposit", headers=bearer(admin)).json()
        if body["items"]:
            tx = body["items"][0]
            for field in ("id", "payer_id", "amount", "type", "status", "created_at"):
                assert field in tx


# ---------------------------------------------------------------------------
# Статистика
# ---------------------------------------------------------------------------

class TestAdminStats:

    def test_returns_200(self, client, admin):
        assert client.get("/admin/stats", headers=bearer(admin)).status_code == 200

    def test_has_all_fields(self, client, admin):
        body = client.get("/admin/stats", headers=bearer(admin)).json()
        for field in ("total_users", "total_employers", "total_workers",
                      "total_orders", "completed_orders", "cancelled_orders",
                      "total_platform_revenue", "total_volume"):
            assert field in body

    def test_counts_are_non_negative(self, client, admin):
        body = client.get("/admin/stats", headers=bearer(admin)).json()
        assert body["total_users"] >= 0
        assert body["total_orders"] >= 0

    def test_employer_count_grows_after_register(self, client, admin):
        before = client.get("/admin/stats", headers=bearer(admin)).json()["total_employers"]
        _register(client, "employer")
        after = client.get("/admin/stats", headers=bearer(admin)).json()["total_employers"]
        assert after == before + 1


# ---------------------------------------------------------------------------
# Отзывы
# ---------------------------------------------------------------------------

class TestAdminReviews:

    def _create_review_in_db(self, client: TestClient, db: Session) -> str:
        from models.order import Order

        _, emp_token = _register(client, "employer")
        _, wrk_token = _register(client, "worker")
        emp_id = uuid.UUID(client.get("/auth/me", headers=bearer(emp_token)).json()["id"])
        wrk_id = uuid.UUID(client.get("/auth/me", headers=bearer(wrk_token)).json()["id"])

        order = Order(
            employer_id=emp_id,
            profession_id=1,
            title="Тест отзыв",
            hours=1,
            hourly_rate=Decimal("100.00"),
            total_price=Decimal("100.00"),
            address="Москва",
            lat=Decimal("55.751244"),
            lng=Decimal("37.618423"),
            status="completed",
            assigned_worker_id=wrk_id,
        )
        db.add(order)
        db.flush()

        review = Review(
            order_id=order.id,
            author_id=emp_id,
            recipient_id=wrk_id,
            rating=5,
        )
        db.add(review)
        db.flush()
        return str(review.id)

    def test_delete_review_returns_204(self, client, admin, db):
        review_id = self._create_review_in_db(client, db)
        resp = client.delete(f"/admin/reviews/{review_id}", headers=bearer(admin))
        assert resp.status_code == 204

    def test_deleted_review_not_found(self, client, admin, db):
        review_id = self._create_review_in_db(client, db)
        client.delete(f"/admin/reviews/{review_id}", headers=bearer(admin))
        resp = client.delete(f"/admin/reviews/{review_id}", headers=bearer(admin))
        assert resp.status_code == 404

    def test_delete_nonexistent_review(self, client, admin):
        resp = client.delete(f"/admin/reviews/{uuid.uuid4()}", headers=bearer(admin))
        assert resp.status_code == 404
