"""
Интеграционные тесты для /orders/ эндпоинтов.

Каждый тест создаёт уникальную профессию внутри своей транзакции (откатывается
после теста), поэтому существующие воркеры из реальной БД не мешают сценариям
"нет доступных исполнителей".
"""
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.profession import Profession
from models.worker_profile import WorkerProfile

ORDER_LAT = "55.751244"
ORDER_LNG = "37.618423"
WORKER_LAT = "55.752000"
WORKER_LNG = "37.619000"

_SVC = "services.order_service"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def unique_email() -> str:
    return f"test_{uuid.uuid4().hex[:12]}@example.com"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, role: str) -> tuple[dict, str]:
    payload = {
        "email": unique_email(),
        "password": "secret12345",
        "last_name": "Тестов",
        "first_name": "Тест",
        "patronymic": None,
        "role": role,
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 201
    return payload, resp.json()["access_token"]


def register_employer(client: TestClient) -> tuple[dict, str]:
    return _register(client, "employer")


def register_worker(client: TestClient) -> tuple[dict, str]:
    return _register(client, "worker")


def get_user_id(client: TestClient, token: str) -> uuid.UUID:
    resp = client.get("/auth/me", headers=bearer(token))
    assert resp.status_code == 200
    return uuid.UUID(resp.json()["id"])


def make_worker_profile(
    db: Session,
    user_id: uuid.UUID,
    profession_id: int,
    *,
    online: bool = True,
    lat: str | None = WORKER_LAT,
    lng: str | None = WORKER_LNG,
) -> WorkerProfile:
    wp = WorkerProfile(
        user_id=user_id,
        profession_id=profession_id,
        is_online=online,
        current_lat=Decimal(lat) if lat else None,
        current_lng=Decimal(lng) if lng else None,
    )
    db.add(wp)
    db.commit()
    db.refresh(wp)
    return wp


def order_payload(profession_id: int, **overrides) -> dict:
    base = {
        "profession_id": profession_id,
        "title": "Тестовый заказ",
        "description": "Описание",
        "hours": 2,
        "hourly_rate": "500.00",
        "address": "Москва, ул. Примерная, 1",
        "lat": ORDER_LAT,
        "lng": ORDER_LNG,
    }
    return {**base, **overrides}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_emails():
    """Глушим все SMTP-вызовы во всех тестах этого файла."""
    with (
        patch(f"{_SVC}.notify_worker_new_offer"),
        patch(f"{_SVC}.notify_employer_worker_accepted"),
        patch(f"{_SVC}.notify_employer_worker_declined"),
        patch(f"{_SVC}.notify_no_workers"),
        patch(f"{_SVC}.notify_order_completed"),
    ):
        yield


@pytest.fixture()
def profession(db: Session) -> int:
    """
    Создаёт уникальную тестовую профессию внутри транзакции теста.
    Гарантирует, что ни один существующий воркер в БД не имеет этой профессии.
    """
    p = Profession(
        id=32000,
        name=f"Тест_{uuid.uuid4().hex[:8]}",
        hourly_rate=Decimal("500.00"),
        rate_unit="hour",
        is_active=True,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


# ---------------------------------------------------------------------------
# POST /orders/
# ---------------------------------------------------------------------------

class TestCreateOrder:

    def test_no_workers_available(self, client, profession):
        _, token = register_employer(client)
        resp = client.post("/orders/", json=order_payload(profession), headers=bearer(token))
        assert resp.status_code == 201
        body = resp.json()
        assert body["order"]["status"] == "no_workers_available"
        assert body["active_offer_id"] is None
        assert body["message"] is not None

    def test_worker_dispatched(self, client, db, profession):
        _, emp_token = register_employer(client)
        _, wrk_token = register_worker(client)
        make_worker_profile(db, get_user_id(client, wrk_token), profession)

        resp = client.post("/orders/", json=order_payload(profession), headers=bearer(emp_token))
        assert resp.status_code == 201
        body = resp.json()
        assert body["order"]["status"] == "pending_offer"
        assert body["active_offer_id"] is not None

    def test_requires_employer_role(self, client, profession):
        _, token = register_worker(client)
        resp = client.post("/orders/", json=order_payload(profession), headers=bearer(token))
        assert resp.status_code == 403

    def test_requires_auth(self, client, profession):
        resp = client.post("/orders/", json=order_payload(profession))
        assert resp.status_code == 401

    def test_invalid_profession(self, client):
        _, token = register_employer(client)
        resp = client.post("/orders/", json=order_payload(9999), headers=bearer(token))
        assert resp.status_code == 400

    def test_invalid_hours_zero(self, client, profession):
        _, token = register_employer(client)
        resp = client.post("/orders/", json=order_payload(profession, hours=0), headers=bearer(token))
        assert resp.status_code == 422

    def test_invalid_hours_too_large(self, client, profession):
        _, token = register_employer(client)
        resp = client.post("/orders/", json=order_payload(profession, hours=200), headers=bearer(token))
        assert resp.status_code == 422

    def test_invalid_coordinates(self, client, profession):
        _, token = register_employer(client)
        resp = client.post("/orders/", json=order_payload(profession, lat="999.0"), headers=bearer(token))
        assert resp.status_code == 422

    def test_total_price_calculated(self, client, db, profession):
        _, emp_token = register_employer(client)
        _, wrk_token = register_worker(client)
        make_worker_profile(db, get_user_id(client, wrk_token), profession)

        resp = client.post(
            "/orders/",
            json=order_payload(profession, hours=3, hourly_rate="400.00"),
            headers=bearer(emp_token),
        )
        assert resp.status_code == 201
        assert resp.json()["order"]["total_price"] == "1200.00"

    def test_offline_worker_not_dispatched(self, client, db, profession):
        _, emp_token = register_employer(client)
        _, wrk_token = register_worker(client)
        make_worker_profile(db, get_user_id(client, wrk_token), profession, online=False)

        resp = client.post("/orders/", json=order_payload(profession), headers=bearer(emp_token))
        assert resp.status_code == 201
        assert resp.json()["order"]["status"] == "no_workers_available"

    def test_worker_without_coords_not_dispatched(self, client, db, profession):
        _, emp_token = register_employer(client)
        _, wrk_token = register_worker(client)
        make_worker_profile(db, get_user_id(client, wrk_token), profession, lat=None, lng=None)

        resp = client.post("/orders/", json=order_payload(profession), headers=bearer(emp_token))
        assert resp.status_code == 201
        assert resp.json()["order"]["status"] == "no_workers_available"

    def test_nearest_worker_gets_offer(self, client, db, profession):
        """Ближайший к заказу воркер должен получить предложение."""
        _, emp_token = register_employer(client)
        _, near_token = register_worker(client)
        _, far_token = register_worker(client)
        near_id = get_user_id(client, near_token)
        far_id = get_user_id(client, far_token)
        make_worker_profile(db, near_id, profession, lat="55.752000", lng="37.619000")
        make_worker_profile(db, far_id, profession, lat="55.800000", lng="37.700000")

        resp = client.post("/orders/", json=order_payload(profession), headers=bearer(emp_token))
        assert resp.status_code == 201
        offer_id = resp.json()["active_offer_id"]

        # Ближний воркер должен увидеть оффер
        offers = client.get("/orders/pending-offers", headers=bearer(near_token)).json()
        assert any(o["offer"]["id"] == offer_id for o in offers)

        # Дальний — не должен
        offers_far = client.get("/orders/pending-offers", headers=bearer(far_token)).json()
        assert len(offers_far) == 0


# ---------------------------------------------------------------------------
# GET /orders/pending-offers
# ---------------------------------------------------------------------------

class TestPendingOffers:

    def test_empty_for_new_worker(self, client):
        _, token = register_worker(client)
        resp = client.get("/orders/pending-offers", headers=bearer(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_offer_when_dispatched(self, client, db, profession):
        _, emp_token = register_employer(client)
        _, wrk_token = register_worker(client)
        make_worker_profile(db, get_user_id(client, wrk_token), profession)

        client.post("/orders/", json=order_payload(profession), headers=bearer(emp_token))

        resp = client.get("/orders/pending-offers", headers=bearer(wrk_token))
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["offer"]["status"] == "sent"
        assert items[0]["order"]["status"] == "pending_offer"

    def test_forbidden_for_employer(self, client):
        _, token = register_employer(client)
        resp = client.get("/orders/pending-offers", headers=bearer(token))
        assert resp.status_code == 403

    def test_requires_auth(self, client):
        resp = client.get("/orders/pending-offers")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /orders/{order_id}
# ---------------------------------------------------------------------------

class TestGetOrder:

    def _create_order(self, client, emp_token, profession) -> str:
        resp = client.post("/orders/", json=order_payload(profession), headers=bearer(emp_token))
        assert resp.status_code == 201
        return resp.json()["order"]["id"]

    def test_employer_can_read_own_order(self, client, profession):
        _, emp_token = register_employer(client)
        order_id = self._create_order(client, emp_token, profession)
        resp = client.get(f"/orders/{order_id}", headers=bearer(emp_token))
        assert resp.status_code == 200
        assert resp.json()["order"]["id"] == order_id

    def test_assigned_worker_can_read_order(self, client, db, profession):
        _, emp_token = register_employer(client)
        _, wrk_token = register_worker(client)
        make_worker_profile(db, get_user_id(client, wrk_token), profession)

        create_resp = client.post("/orders/", json=order_payload(profession), headers=bearer(emp_token))
        order_id = create_resp.json()["order"]["id"]
        offer_id = create_resp.json()["active_offer_id"]

        client.post(f"/orders/offers/{offer_id}/respond", json={"accept": True}, headers=bearer(wrk_token))

        resp = client.get(f"/orders/{order_id}", headers=bearer(wrk_token))
        assert resp.status_code == 200

    def test_third_party_forbidden(self, client, profession):
        _, emp_token = register_employer(client)
        order_id = self._create_order(client, emp_token, profession)

        _, other_token = register_employer(client)
        resp = client.get(f"/orders/{order_id}", headers=bearer(other_token))
        assert resp.status_code == 403

    def test_not_found(self, client):
        _, token = register_employer(client)
        resp = client.get(f"/orders/{uuid.uuid4()}", headers=bearer(token))
        assert resp.status_code == 404

    def test_requires_auth(self, client, profession):
        _, token = register_employer(client)
        order_id = self._create_order(client, token, profession)
        resp = client.get(f"/orders/{order_id}")
        assert resp.status_code == 401

    def test_assigned_worker_in_response_after_accept(self, client, db, profession):
        _, emp_token = register_employer(client)
        _, wrk_token = register_worker(client)
        make_worker_profile(db, get_user_id(client, wrk_token), profession)

        create_resp = client.post("/orders/", json=order_payload(profession), headers=bearer(emp_token))
        order_id = create_resp.json()["order"]["id"]
        offer_id = create_resp.json()["active_offer_id"]

        client.post(f"/orders/offers/{offer_id}/respond", json={"accept": True}, headers=bearer(wrk_token))

        resp = client.get(f"/orders/{order_id}", headers=bearer(emp_token))
        body = resp.json()
        assert body["order"]["status"] == "assigned"
        assert body["assigned_worker"] is not None

    def test_no_assigned_worker_before_accept(self, client, profession):
        _, emp_token = register_employer(client)
        order_id = self._create_order(client, emp_token, profession)
        body = client.get(f"/orders/{order_id}", headers=bearer(emp_token)).json()
        assert body["assigned_worker"] is None


# ---------------------------------------------------------------------------
# POST /orders/offers/{offer_id}/respond
# ---------------------------------------------------------------------------

class TestRespondToOffer:

    def _setup_offer(self, client, db, profession) -> tuple[str, str, str, str]:
        """Возвращает (order_id, offer_id, emp_token, wrk_token)."""
        _, emp_token = register_employer(client)
        _, wrk_token = register_worker(client)
        make_worker_profile(db, get_user_id(client, wrk_token), profession)

        resp = client.post("/orders/", json=order_payload(profession), headers=bearer(emp_token))
        assert resp.status_code == 201
        return resp.json()["order"]["id"], resp.json()["active_offer_id"], emp_token, wrk_token

    def test_accept_assigns_order(self, client, db, profession):
        order_id, offer_id, _, wrk_token = self._setup_offer(client, db, profession)
        resp = client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": True},
            headers=bearer(wrk_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["order"]["status"] == "assigned"
        assert body["order"]["assigned_worker_id"] is not None
        assert body["worker"]["id"] == str(get_user_id(client, wrk_token))

    def test_accept_returns_worker_location(self, client, db, profession):
        _, offer_id, _, wrk_token = self._setup_offer(client, db, profession)
        resp = client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": True},
            headers=bearer(wrk_token),
        )
        assert resp.status_code == 200
        location = resp.json()["worker"]["location"]
        assert location["lat"] is not None
        assert location["source"] == "worker_profile"

    def test_decline_no_next_worker(self, client, db, profession):
        _, offer_id, _, wrk_token = self._setup_offer(client, db, profession)
        resp = client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": False},
            headers=bearer(wrk_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["next_offer_id"] is None
        assert body["order"]["status"] == "no_workers_available"

    def test_decline_dispatches_next_worker(self, client, db, profession):
        _, emp_token = register_employer(client)
        _, wrk1_token = register_worker(client)
        _, wrk2_token = register_worker(client)
        wrk1_id = get_user_id(client, wrk1_token)
        wrk2_id = get_user_id(client, wrk2_token)
        # Ближний к заказу воркер получит первый оффер
        make_worker_profile(db, wrk1_id, profession, lat="55.752000", lng="37.619000")
        make_worker_profile(db, wrk2_id, profession, lat="55.800000", lng="37.700000")

        create_resp = client.post("/orders/", json=order_payload(profession), headers=bearer(emp_token))
        first_offer_id = create_resp.json()["active_offer_id"]

        # Первый воркер отказывается — должен быть найден второй
        resp = client.post(
            f"/orders/offers/{first_offer_id}/respond",
            json={"accept": False},
            headers=bearer(wrk1_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["next_offer_id"] is not None
        assert body["order"]["status"] == "pending_offer"

    def test_wrong_worker_gets_404(self, client, db, profession):
        _, offer_id, _, _ = self._setup_offer(client, db, profession)
        _, other_wrk_token = register_worker(client)
        resp = client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": True},
            headers=bearer(other_wrk_token),
        )
        assert resp.status_code == 404

    def test_accept_twice_conflicts(self, client, db, profession):
        _, offer_id, _, wrk_token = self._setup_offer(client, db, profession)
        client.post(f"/orders/offers/{offer_id}/respond", json={"accept": True}, headers=bearer(wrk_token))
        resp = client.post(f"/orders/offers/{offer_id}/respond", json={"accept": True}, headers=bearer(wrk_token))
        assert resp.status_code == 409

    def test_employer_cannot_respond(self, client, db, profession):
        _, offer_id, emp_token, _ = self._setup_offer(client, db, profession)
        resp = client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": True},
            headers=bearer(emp_token),
        )
        assert resp.status_code == 403

    def test_requires_auth(self, client, db, profession):
        _, offer_id, _, _ = self._setup_offer(client, db, profession)
        resp = client.post(f"/orders/offers/{offer_id}/respond", json={"accept": True})
        assert resp.status_code == 401

    def test_nonexistent_offer(self, client):
        _, token = register_worker(client)
        resp = client.post(
            f"/orders/offers/{uuid.uuid4()}/respond",
            json={"accept": True},
            headers=bearer(token),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /orders/{order_id}/complete
# ---------------------------------------------------------------------------

class TestCompleteOrder:

    def _setup_assigned_order(self, client, db, profession) -> tuple[str, str, str]:
        """Создаёт заказ в статусе assigned. Возвращает (order_id, emp_token, wrk_token)."""
        _, emp_token = register_employer(client)
        _, wrk_token = register_worker(client)
        make_worker_profile(db, get_user_id(client, wrk_token), profession)

        create_resp = client.post("/orders/", json=order_payload(profession), headers=bearer(emp_token))
        order_id = create_resp.json()["order"]["id"]
        offer_id = create_resp.json()["active_offer_id"]

        r = client.post(f"/orders/offers/{offer_id}/respond", json={"accept": True}, headers=bearer(wrk_token))
        assert r.status_code == 200
        assert r.json()["order"]["status"] == "assigned"
        return order_id, emp_token, wrk_token

    def test_employer_can_complete(self, client, db, profession):
        order_id, emp_token, _ = self._setup_assigned_order(client, db, profession)
        resp = client.patch(f"/orders/{order_id}/complete", headers=bearer(emp_token))
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    def test_assigned_worker_can_complete(self, client, db, profession):
        order_id, _, wrk_token = self._setup_assigned_order(client, db, profession)
        resp = client.patch(f"/orders/{order_id}/complete", headers=bearer(wrk_token))
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    def test_third_party_forbidden(self, client, db, profession):
        order_id, _, _ = self._setup_assigned_order(client, db, profession)
        _, other_token = register_employer(client)
        resp = client.patch(f"/orders/{order_id}/complete", headers=bearer(other_token))
        assert resp.status_code == 403

    def test_cannot_complete_pending_order(self, client, profession):
        _, emp_token = register_employer(client)
        create_resp = client.post("/orders/", json=order_payload(profession), headers=bearer(emp_token))
        order_id = create_resp.json()["order"]["id"]
        resp = client.patch(f"/orders/{order_id}/complete", headers=bearer(emp_token))
        assert resp.status_code == 409

    def test_cannot_complete_twice(self, client, db, profession):
        order_id, emp_token, _ = self._setup_assigned_order(client, db, profession)
        client.patch(f"/orders/{order_id}/complete", headers=bearer(emp_token))
        resp = client.patch(f"/orders/{order_id}/complete", headers=bearer(emp_token))
        assert resp.status_code == 409

    def test_not_found(self, client):
        _, token = register_employer(client)
        resp = client.patch(f"/orders/{uuid.uuid4()}/complete", headers=bearer(token))
        assert resp.status_code == 404

    def test_requires_auth(self, client, db, profession):
        order_id, _, _ = self._setup_assigned_order(client, db, profession)
        resp = client.patch(f"/orders/{order_id}/complete")
        assert resp.status_code == 401

    def test_completed_orders_counter_incremented(self, client, db, profession):
        order_id, emp_token, wrk_token = self._setup_assigned_order(client, db, profession)
        worker_id = get_user_id(client, wrk_token)

        client.patch(f"/orders/{order_id}/complete", headers=bearer(emp_token))

        db.expire_all()
        from sqlalchemy import select
        wp = db.execute(
            select(WorkerProfile).where(WorkerProfile.user_id == worker_id)
        ).scalar_one()
        assert wp.completed_orders == 1
