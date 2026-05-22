"""
Интеграционные тесты для /messages/ эндпоинтов (чат по заказу).
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
_EXP = "services.offer_expiry"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def unique_email() -> str:
    return f"chat_{uuid.uuid4().hex[:12]}@example.com"


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
    return uuid.UUID(resp.json()["id"])


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


def order_payload(profession_id: int) -> dict:
    return {
        "profession_id": profession_id,
        "title": "Чат-заказ",
        "hours": 2,
        "hourly_rate": "500.00",
        "address": "Москва, ул. Примерная, 1",
        "lat": ORDER_LAT,
        "lng": ORDER_LNG,
    }


def create_assigned_order(client: TestClient, db: Session, profession: int):
    """Создаёт заказ и сразу принимает его — возвращает (order_id, emp_token, wrk_token)."""
    _, emp_token = register_employer(client)
    _, wrk_token = register_worker(client)
    make_worker_profile(db, get_user_id(client, wrk_token), profession)

    create_resp = client.post("/orders/", json=order_payload(profession), headers=bearer(emp_token))
    assert create_resp.json()["order"]["status"] == "pending_offer"
    order_id = create_resp.json()["order"]["id"]
    offer_id = create_resp.json()["active_offer_id"]

    client.post(f"/orders/offers/{offer_id}/respond", json={"accept": True}, headers=bearer(wrk_token))
    return order_id, emp_token, wrk_token


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
        id=32001,
        name=f"ЧатТест_{uuid.uuid4().hex[:8]}",
        hourly_rate=Decimal("500.00"),
        rate_unit="hour",
        is_active=True,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


# ---------------------------------------------------------------------------
# Отправка сообщений
# ---------------------------------------------------------------------------

class TestSendMessage:

    def test_employer_sends_message(self, client, db, profession):
        order_id, emp_token, _ = create_assigned_order(client, db, profession)
        resp = client.post(f"/messages/{order_id}", json={"text": "Привет!"}, headers=bearer(emp_token))
        assert resp.status_code == 201
        assert resp.json()["text"] == "Привет!"
        assert resp.json()["order_id"] == order_id

    def test_worker_sends_message(self, client, db, profession):
        order_id, _, wrk_token = create_assigned_order(client, db, profession)
        resp = client.post(f"/messages/{order_id}", json={"text": "Буду через 20 минут"}, headers=bearer(wrk_token))
        assert resp.status_code == 201
        assert resp.json()["text"] == "Буду через 20 минут"

    def test_cannot_send_to_nonexistent_order(self, client, db, profession):
        _, emp_token = register_employer(client)
        resp = client.post(f"/messages/{uuid.uuid4()}", json={"text": "Тест"}, headers=bearer(emp_token))
        assert resp.status_code == 404

    def test_stranger_cannot_send(self, client, db, profession):
        order_id, _, _ = create_assigned_order(client, db, profession)
        _, stranger_token = register_employer(client)
        resp = client.post(f"/messages/{order_id}", json={"text": "Хакер"}, headers=bearer(stranger_token))
        assert resp.status_code == 403

    def test_cannot_send_to_pending_offer_order(self, client, db, profession):
        _, emp_token = register_employer(client)
        # Заказ без воркера — статус no_workers_available.
        create_resp = client.post("/orders/", json=order_payload(profession), headers=bearer(emp_token))
        order_id = create_resp.json()["order"]["id"]
        resp = client.post(f"/messages/{order_id}", json={"text": "Привет"}, headers=bearer(emp_token))
        assert resp.status_code == 409

    def test_empty_text_rejected(self, client, db, profession):
        order_id, emp_token, _ = create_assigned_order(client, db, profession)
        resp = client.post(f"/messages/{order_id}", json={"text": ""}, headers=bearer(emp_token))
        assert resp.status_code == 422

    def test_text_stripped(self, client, db, profession):
        order_id, emp_token, _ = create_assigned_order(client, db, profession)
        resp = client.post(f"/messages/{order_id}", json={"text": "  пробелы  "}, headers=bearer(emp_token))
        assert resp.status_code == 201
        assert resp.json()["text"] == "пробелы"

    def test_unauthenticated_rejected(self, client, db, profession):
        order_id, _, _ = create_assigned_order(client, db, profession)
        resp = client.post(f"/messages/{order_id}", json={"text": "Тест"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# История сообщений
# ---------------------------------------------------------------------------

class TestGetMessages:

    def test_empty_history(self, client, db, profession):
        order_id, emp_token, _ = create_assigned_order(client, db, profession)
        resp = client.get(f"/messages/{order_id}", headers=bearer(emp_token))
        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["next_cursor"] is None

    def test_messages_returned_newest_first(self, client, db, profession):
        order_id, emp_token, wrk_token = create_assigned_order(client, db, profession)
        client.post(f"/messages/{order_id}", json={"text": "Первое"}, headers=bearer(emp_token))
        client.post(f"/messages/{order_id}", json={"text": "Второе"}, headers=bearer(wrk_token))
        client.post(f"/messages/{order_id}", json={"text": "Третье"}, headers=bearer(emp_token))

        resp = client.get(f"/messages/{order_id}", headers=bearer(emp_token))
        texts = [m["text"] for m in resp.json()["items"]]
        assert texts == ["Третье", "Второе", "Первое"]

    def test_both_participants_see_same_history(self, client, db, profession):
        order_id, emp_token, wrk_token = create_assigned_order(client, db, profession)
        client.post(f"/messages/{order_id}", json={"text": "Привет"}, headers=bearer(emp_token))

        emp_resp = client.get(f"/messages/{order_id}", headers=bearer(emp_token))
        wrk_resp = client.get(f"/messages/{order_id}", headers=bearer(wrk_token))
        assert emp_resp.json()["items"] == wrk_resp.json()["items"]

    def test_cursor_pagination(self, client, db, profession):
        order_id, emp_token, _ = create_assigned_order(client, db, profession)
        for i in range(5):
            client.post(f"/messages/{order_id}", json={"text": f"msg{i}"}, headers=bearer(emp_token))

        # Первая страница — 3 сообщения
        resp1 = client.get(f"/messages/{order_id}", params={"limit": 3}, headers=bearer(emp_token))
        assert resp1.status_code == 200
        page1 = resp1.json()
        assert len(page1["items"]) == 3
        assert page1["next_cursor"] is not None

        # Вторая страница по курсору
        resp2 = client.get(
            f"/messages/{order_id}",
            params={"limit": 3, "before": page1["next_cursor"]},
            headers=bearer(emp_token),
        )
        page2 = resp2.json()
        assert len(page2["items"]) == 2
        assert page2["next_cursor"] is None

        # Нет пересечений между страницами
        ids1 = {m["id"] for m in page1["items"]}
        ids2 = {m["id"] for m in page2["items"]}
        assert ids1.isdisjoint(ids2)

    def test_stranger_cannot_read(self, client, db, profession):
        order_id, _, _ = create_assigned_order(client, db, profession)
        _, stranger_token = register_worker(client)
        resp = client.get(f"/messages/{order_id}", headers=bearer(stranger_token))
        assert resp.status_code == 403

    def test_cannot_read_non_assigned_order(self, client, db, profession):
        _, emp_token = register_employer(client)
        create_resp = client.post("/orders/", json=order_payload(profession), headers=bearer(emp_token))
        order_id = create_resp.json()["order"]["id"]
        resp = client.get(f"/messages/{order_id}", headers=bearer(emp_token))
        assert resp.status_code == 409

    def test_sender_id_correct(self, client, db, profession):
        order_id, emp_token, _ = create_assigned_order(client, db, profession)
        emp_id = get_user_id(client, emp_token)
        client.post(f"/messages/{order_id}", json={"text": "Тест"}, headers=bearer(emp_token))

        resp = client.get(f"/messages/{order_id}", headers=bearer(emp_token))
        assert resp.json()["items"][0]["sender_id"] == str(emp_id)
