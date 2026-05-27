"""
Интеграционные тесты для offer-эндпоинтов:
  - POST /orders/offers/{offer_id}/respond  (принять / отклонить)
  - GET  /orders/pending-offers             (входящие офферы воркера)

test_orders_api.py::TestRespondToOffer уже покрывает базовые accept/decline сценарии.
Здесь — структура ответов, переходы статуса оффера, цепочка диспетчеризации
и полное покрытие GET /orders/pending-offers.
"""
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.order_offer import OrderOffer
from models.profession import Profession
from models.worker_profile import WorkerProfile
from utils.enums import OfferStatus

ORDER_LAT = "55.751244"
ORDER_LNG = "37.618423"

# Два воркера: ближний и дальний — для тестов цепочки диспетчеризации
NEAR_LAT = "55.752000"
NEAR_LNG = "37.619000"
FAR_LAT  = "55.800000"
FAR_LNG  = "37.700000"

_SVC = "services.order_service"
_EXP = "services.offer_expiry"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def unique_email() -> str:
    return f"off_{uuid.uuid4().hex[:12]}@example.com"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, role: str) -> tuple[dict, str]:
    payload = {
        "email": unique_email(),
        "password": "secret12345",
        "last_name": "Офферов",
        "first_name": "Тест",
        "patronymic": None,
        "role": role,
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 201
    return payload, resp.json()["access_token"]


def get_user_id(client: TestClient, token: str) -> uuid.UUID:
    return uuid.UUID(client.get("/auth/me", headers=bearer(token)).json()["id"])


def make_worker_profile(
    db: Session,
    user_id: uuid.UUID,
    profession_id: int,
    *,
    lat: str = NEAR_LAT,
    lng: str = NEAR_LNG,
) -> WorkerProfile:
    wp = WorkerProfile(
        user_id=user_id,
        profession_id=profession_id,
        is_online=True,
        current_lat=Decimal(lat),
        current_lng=Decimal(lng),
    )
    db.add(wp)
    db.commit()
    db.refresh(wp)
    return wp


def _order_payload(profession_id: int) -> dict:
    return {
        "profession_id": profession_id,
        "title": "Тест оффера",
        "description": None,
        "hours": 2,
        "hourly_rate": "500.00",
        "address": "Москва, тест",
        "lat": ORDER_LAT,
        "lng": ORDER_LNG,
    }


def _create_order_with_offer(
    client: TestClient,
    db: Session,
    profession_id: int,
    *,
    worker_lat: str = NEAR_LAT,
    worker_lng: str = NEAR_LNG,
) -> tuple[str, str, str, str]:
    """
    Регистрирует работодателя и воркера, создаёт заказ.
    Возвращает (order_id, offer_id, emp_token, wrk_token).
    """
    _, emp_token = _register(client, "employer")
    _, wrk_token = _register(client, "worker")
    make_worker_profile(db, get_user_id(client, wrk_token), profession_id,
                        lat=worker_lat, lng=worker_lng)

    resp = client.post("/orders/", json=_order_payload(profession_id), headers=bearer(emp_token))
    assert resp.status_code == 201
    data = resp.json()
    return data["order"]["id"], data["active_offer_id"], emp_token, wrk_token


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
def profession(db: Session) -> int:
    p = Profession(
        id=32500,
        name=f"ОфферТест_{uuid.uuid4().hex[:8]}",
        hourly_rate=Decimal("500.00"),
        rate_unit="hour",
        is_active=True,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id



# ---------------------------------------------------------------------------
# POST /orders/offers/{offer_id}/respond — структура ответа при accept
# ---------------------------------------------------------------------------

class TestAcceptOfferResponse:

    def test_response_has_order_and_worker(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        resp = client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": True},
            headers=bearer(wrk_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "order" in body
        assert "worker" in body

    def test_order_status_is_assigned(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        resp = client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": True},
            headers=bearer(wrk_token),
        )
        assert resp.json()["order"]["status"] == "assigned"

    def test_order_assigned_worker_id_matches(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        wrk_id = str(get_user_id(client, wrk_token))
        resp = client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": True},
            headers=bearer(wrk_token),
        )
        assert resp.json()["order"]["assigned_worker_id"] == wrk_id

    def test_worker_object_has_required_fields(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        resp = client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": True},
            headers=bearer(wrk_token),
        )
        worker = resp.json()["worker"]
        for field in ("id", "email", "last_name", "first_name",
                      "rating_avg", "reviews_count", "completed_orders", "location"):
            assert field in worker, f"Missing field: {field}"

    def test_worker_location_has_coordinates(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        resp = client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": True},
            headers=bearer(wrk_token),
        )
        loc = resp.json()["worker"]["location"]
        assert loc["lat"] is not None
        assert loc["lng"] is not None

    def test_worker_location_source_is_worker_profile(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        resp = client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": True},
            headers=bearer(wrk_token),
        )
        assert resp.json()["worker"]["location"]["source"] == "worker_profile"

    def test_offer_status_becomes_accepted_in_db(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": True},
            headers=bearer(wrk_token),
        )
        db.expire_all()
        offer = db.get(OrderOffer, uuid.UUID(offer_id))
        assert offer.status == OfferStatus.accepted.value
        assert offer.responded_at is not None


# ---------------------------------------------------------------------------
# POST /orders/offers/{offer_id}/respond — структура ответа при decline
# ---------------------------------------------------------------------------

class TestDeclineOfferResponse:

    def test_response_has_declined_flag(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        resp = client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": False},
            headers=bearer(wrk_token),
        )
        assert resp.status_code == 200
        assert resp.json()["declined"] is True

    def test_response_has_order_and_next_offer_fields(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        resp = client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": False},
            headers=bearer(wrk_token),
        )
        body = resp.json()
        assert "order" in body
        assert "next_offer_id" in body
        assert "message" in body

    def test_offer_status_becomes_declined_in_db(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": False},
            headers=bearer(wrk_token),
        )
        db.expire_all()
        offer = db.get(OrderOffer, uuid.UUID(offer_id))
        assert offer.status == OfferStatus.declined.value
        assert offer.responded_at is not None

    def test_decline_no_next_worker_sets_no_workers_available(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        resp = client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": False},
            headers=bearer(wrk_token),
        )
        body = resp.json()
        assert body["next_offer_id"] is None
        assert body["order"]["status"] == "no_workers_available"

    def test_decline_with_next_worker_order_stays_pending(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        _, wrk1_token = _register(client, "worker")
        _, wrk2_token = _register(client, "worker")
        make_worker_profile(db, get_user_id(client, wrk1_token), profession,
                            lat=NEAR_LAT, lng=NEAR_LNG)
        make_worker_profile(db, get_user_id(client, wrk2_token), profession,
                            lat=FAR_LAT, lng=FAR_LNG)

        create_resp = client.post("/orders/", json=_order_payload(profession), headers=bearer(emp_token))
        first_offer_id = create_resp.json()["active_offer_id"]

        resp = client.post(
            f"/orders/offers/{first_offer_id}/respond",
            json={"accept": False},
            headers=bearer(wrk1_token),
        )
        body = resp.json()
        assert body["next_offer_id"] is not None
        assert body["order"]["status"] == "pending_offer"

    def test_declined_worker_not_offered_again(self, client, db, profession):
        """
        Воркер1 отклоняет → оффер уходит воркеру2.
        Воркер2 тоже отклоняет → нет других кандидатов.
        Воркер1 не получает повторный оффер.
        """
        _, emp_token = _register(client, "employer")
        _, wrk1_token = _register(client, "worker")
        _, wrk2_token = _register(client, "worker")
        make_worker_profile(db, get_user_id(client, wrk1_token), profession,
                            lat=NEAR_LAT, lng=NEAR_LNG)
        make_worker_profile(db, get_user_id(client, wrk2_token), profession,
                            lat=FAR_LAT, lng=FAR_LNG)

        create_resp = client.post("/orders/", json=_order_payload(profession), headers=bearer(emp_token))
        first_offer_id = create_resp.json()["active_offer_id"]

        decline1 = client.post(
            f"/orders/offers/{first_offer_id}/respond",
            json={"accept": False},
            headers=bearer(wrk1_token),
        )
        second_offer_id = decline1.json()["next_offer_id"]
        assert second_offer_id is not None

        decline2 = client.post(
            f"/orders/offers/{second_offer_id}/respond",
            json={"accept": False},
            headers=bearer(wrk2_token),
        )
        # Воркер1 уже в excluded → следующего кандидата нет
        assert decline2.json()["next_offer_id"] is None
        assert decline2.json()["order"]["status"] == "no_workers_available"

    def test_second_worker_accepts_after_first_declined(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        _, wrk1_token = _register(client, "worker")
        _, wrk2_token = _register(client, "worker")
        make_worker_profile(db, get_user_id(client, wrk1_token), profession,
                            lat=NEAR_LAT, lng=NEAR_LNG)
        make_worker_profile(db, get_user_id(client, wrk2_token), profession,
                            lat=FAR_LAT, lng=FAR_LNG)

        create_resp = client.post("/orders/", json=_order_payload(profession), headers=bearer(emp_token))
        first_offer_id = create_resp.json()["active_offer_id"]

        decline = client.post(
            f"/orders/offers/{first_offer_id}/respond",
            json={"accept": False},
            headers=bearer(wrk1_token),
        )
        second_offer_id = decline.json()["next_offer_id"]

        accept = client.post(
            f"/orders/offers/{second_offer_id}/respond",
            json={"accept": True},
            headers=bearer(wrk2_token),
        )
        assert accept.status_code == 200
        assert accept.json()["order"]["status"] == "assigned"
        wrk2_id = str(get_user_id(client, wrk2_token))
        assert accept.json()["order"]["assigned_worker_id"] == wrk2_id


# ---------------------------------------------------------------------------
# POST /orders/offers/{offer_id}/respond — граничные случаи
# ---------------------------------------------------------------------------

class TestRespondOfferEdgeCases:

    def test_respond_to_already_accepted_offer_returns_409(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        client.post(f"/orders/offers/{offer_id}/respond",
                    json={"accept": True}, headers=bearer(wrk_token))
        resp = client.post(f"/orders/offers/{offer_id}/respond",
                           json={"accept": False}, headers=bearer(wrk_token))
        assert resp.status_code == 409

    def test_respond_to_declined_offer_returns_409(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        client.post(f"/orders/offers/{offer_id}/respond",
                    json={"accept": False}, headers=bearer(wrk_token))
        resp = client.post(f"/orders/offers/{offer_id}/respond",
                           json={"accept": True}, headers=bearer(wrk_token))
        assert resp.status_code == 409

    def test_worker_with_existing_assigned_order_cannot_accept(self, client, db, profession):
        """Защита от гонки: воркер принял заказ1, для заказа2 оффер создан вручную в БД."""
        _, emp1_token = _register(client, "employer")
        _, emp2_token = _register(client, "employer")
        _, wrk_token = _register(client, "worker")
        wrk_id = get_user_id(client, wrk_token)

        make_worker_profile(db, wrk_id, profession)

        # Заказ1 — воркер получает оффер и принимает
        r1 = client.post("/orders/", json=_order_payload(profession), headers=bearer(emp1_token))
        offer1_id = r1.json()["active_offer_id"]
        accept1 = client.post(f"/orders/offers/{offer1_id}/respond",
                               json={"accept": True}, headers=bearer(wrk_token))
        assert accept1.json()["order"]["status"] == "assigned"

        # Заказ2 — создаём в БД напрямую и прикрепляем оффер к воркеру (эмуляция гонки)
        from repositories.order_repository import create_order as repo_create_order
        from repositories.offer_repository import create_offer as repo_create_offer
        from utils.enums import OrderStatus

        order2 = repo_create_order(
            db,
            employer_id=get_user_id(client, emp2_token),
            profession_id=profession,
            title="Тест гонки",
            description=None,
            hours=1,
            hourly_rate=Decimal("100.00"),
            total_price=Decimal("100.00"),
            address="Тест",
            lat=Decimal(ORDER_LAT),
            lng=Decimal(ORDER_LNG),
            scheduled_at=None,
            status=OrderStatus.pending_offer.value,
        )
        offer2 = repo_create_offer(db, order_id=order2.id, worker_id=wrk_id, distance_meters=100)

        # Воркер пытается принять второй оффер — уже есть активный заказ
        resp = client.post(f"/orders/offers/{offer2.id}/respond",
                           json={"accept": True}, headers=bearer(wrk_token))
        assert resp.status_code == 409

    def test_cancelled_order_offer_cannot_be_accepted(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        _, wrk_token = _register(client, "worker")
        make_worker_profile(db, get_user_id(client, wrk_token), profession)

        create_resp = client.post("/orders/", json=_order_payload(profession), headers=bearer(emp_token))
        order_id = create_resp.json()["order"]["id"]
        offer_id = create_resp.json()["active_offer_id"]

        # Заказчик отменяет заказ
        client.patch(f"/orders/{order_id}/cancel", headers=bearer(emp_token))

        resp = client.post(f"/orders/offers/{offer_id}/respond",
                           json={"accept": True}, headers=bearer(wrk_token))
        assert resp.status_code == 409

    def test_unauthenticated_returns_401(self, client, db, profession):
        _, offer_id, _, _ = _create_order_with_offer(client, db, profession)
        resp = client.post(f"/orders/offers/{offer_id}/respond", json={"accept": True})
        assert resp.status_code == 401

    def test_employer_returns_403(self, client, db, profession):
        _, offer_id, emp_token, _ = _create_order_with_offer(client, db, profession)
        resp = client.post(f"/orders/offers/{offer_id}/respond",
                           json={"accept": True}, headers=bearer(emp_token))
        assert resp.status_code == 403

    def test_other_worker_returns_404(self, client, db, profession):
        _, offer_id, _, _ = _create_order_with_offer(client, db, profession)
        _, other_wrk_token = _register(client, "worker")
        resp = client.post(f"/orders/offers/{offer_id}/respond",
                           json={"accept": True}, headers=bearer(other_wrk_token))
        assert resp.status_code == 404

    def test_nonexistent_offer_returns_404(self, client):
        _, token = _register(client, "worker")
        resp = client.post(f"/orders/offers/{uuid.uuid4()}/respond",
                           json={"accept": True}, headers=bearer(token))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /orders/pending-offers
# ---------------------------------------------------------------------------

class TestPendingOffers:

    def test_returns_list(self, client, db, profession):
        _, _, _, wrk_token = _create_order_with_offer(client, db, profession)
        resp = client.get("/orders/pending-offers", headers=bearer(wrk_token))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_contains_incoming_offer(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        resp = client.get("/orders/pending-offers", headers=bearer(wrk_token))
        offer_ids = [item["offer"]["id"] for item in resp.json()]
        assert offer_id in offer_ids

    def test_response_item_has_offer_and_order(self, client, db, profession):
        _, _, _, wrk_token = _create_order_with_offer(client, db, profession)
        resp = client.get("/orders/pending-offers", headers=bearer(wrk_token))
        item = resp.json()[0]
        assert "offer" in item
        assert "order" in item

    def test_offer_fields_present(self, client, db, profession):
        _, _, _, wrk_token = _create_order_with_offer(client, db, profession)
        resp = client.get("/orders/pending-offers", headers=bearer(wrk_token))
        offer = resp.json()[0]["offer"]
        for field in ("id", "order_id", "worker_id", "distance_meters", "status", "sent_at"):
            assert field in offer, f"Missing field: {field}"

    def test_offer_status_is_sent(self, client, db, profession):
        _, _, _, wrk_token = _create_order_with_offer(client, db, profession)
        resp = client.get("/orders/pending-offers", headers=bearer(wrk_token))
        assert resp.json()[0]["offer"]["status"] == "sent"

    def test_order_fields_present(self, client, db, profession):
        _, _, _, wrk_token = _create_order_with_offer(client, db, profession)
        resp = client.get("/orders/pending-offers", headers=bearer(wrk_token))
        order = resp.json()[0]["order"]
        for field in ("id", "title", "address", "total_price", "status", "hours", "hourly_rate"):
            assert field in order, f"Missing field: {field}"

    def test_order_status_is_pending_offer(self, client, db, profession):
        _, _, _, wrk_token = _create_order_with_offer(client, db, profession)
        resp = client.get("/orders/pending-offers", headers=bearer(wrk_token))
        assert resp.json()[0]["order"]["status"] == "pending_offer"

    def test_empty_when_no_offers(self, client, profession):
        _, wrk_token = _register(client, "worker")
        resp = client.get("/orders/pending-offers", headers=bearer(wrk_token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_other_worker_offer_not_visible(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        _, other_wrk_token = _register(client, "worker")
        resp = client.get("/orders/pending-offers", headers=bearer(other_wrk_token))
        offer_ids = [item["offer"]["id"] for item in resp.json()]
        assert offer_id not in offer_ids

    def test_disappears_after_accept(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        client.post(f"/orders/offers/{offer_id}/respond",
                    json={"accept": True}, headers=bearer(wrk_token))
        resp = client.get("/orders/pending-offers", headers=bearer(wrk_token))
        assert resp.json() == []

    def test_disappears_after_decline(self, client, db, profession):
        _, offer_id, _, wrk_token = _create_order_with_offer(client, db, profession)
        client.post(f"/orders/offers/{offer_id}/respond",
                    json={"accept": False}, headers=bearer(wrk_token))
        resp = client.get("/orders/pending-offers", headers=bearer(wrk_token))
        assert resp.json() == []

    def test_employer_cannot_access(self, client, db, profession):
        _, _, emp_token, _ = _create_order_with_offer(client, db, profession)
        resp = client.get("/orders/pending-offers", headers=bearer(emp_token))
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/orders/pending-offers")
        assert resp.status_code == 401
