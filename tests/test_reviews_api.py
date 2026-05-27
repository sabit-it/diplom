"""
Интеграционные тесты для /reviews/ эндпоинтов.

Каждый тест изолирован savepoint-транзакцией (conftest.py).
Профессия с id=33000 создаётся per-test и откатывается — реальные воркеры
из БД не мешают сценариям dispatch.
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def unique_email() -> str:
    return f"rev_{uuid.uuid4().hex[:12]}@example.com"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, role: str) -> tuple[dict, str]:
    payload = {
        "email": unique_email(),
        "password": "secret12345",
        "last_name": "Отзывов",
        "first_name": "Тест",
        "patronymic": None,
        "role": role,
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 201
    return payload, resp.json()["access_token"]


def get_user_id(client: TestClient, token: str) -> uuid.UUID:
    return uuid.UUID(client.get("/auth/me", headers=bearer(token)).json()["id"])


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


def _order_payload(profession_id: int) -> dict:
    return {
        "profession_id": profession_id,
        "title": "Тестовый заказ",
        "description": "Описание",
        "hours": 2,
        "hourly_rate": "500.00",
        "address": "Москва, ул. Тест, 1",
        "lat": ORDER_LAT,
        "lng": ORDER_LNG,
    }


def _setup_completed_order(
    client: TestClient,
    db: Session,
    profession_id: int,
) -> tuple[str, str, str]:
    """
    Создаёт заказ в статусе completed.
    Возвращает (order_id, emp_token, wrk_token).
    """
    _, emp_token = _register(client, "employer")
    _, wrk_token = _register(client, "worker")
    make_worker_profile(db, get_user_id(client, wrk_token), profession_id)

    create_resp = client.post(
        "/orders/",
        json=_order_payload(profession_id),
        headers=bearer(emp_token),
    )
    assert create_resp.status_code == 201
    order_id = create_resp.json()["order"]["id"]
    offer_id = create_resp.json()["active_offer_id"]

    accept = client.post(
        f"/orders/offers/{offer_id}/respond",
        json={"accept": True},
        headers=bearer(wrk_token),
    )
    assert accept.json()["order"]["status"] == "assigned"

    complete = client.patch(f"/orders/{order_id}/complete", headers=bearer(emp_token))
    assert complete.json()["status"] == "completed"

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
        id=31500,
        name=f"RevТест_{uuid.uuid4().hex[:8]}",
        hourly_rate=Decimal("500.00"),
        rate_unit="hour",
        is_active=True,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


# ---------------------------------------------------------------------------
# POST /reviews/
# ---------------------------------------------------------------------------

class TestPostReview:

    def test_employer_can_review_worker(self, client, db, profession):
        order_id, emp_token, _ = _setup_completed_order(client, db, profession)
        resp = client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 5, "text": "Отличная работа"},
            headers=bearer(emp_token),
        )
        assert resp.status_code == 201

    def test_worker_can_review_employer(self, client, db, profession):
        order_id, _, wrk_token = _setup_completed_order(client, db, profession)
        resp = client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 4},
            headers=bearer(wrk_token),
        )
        assert resp.status_code == 201

    def test_response_has_required_fields(self, client, db, profession):
        order_id, emp_token, _ = _setup_completed_order(client, db, profession)
        resp = client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 3, "text": "Неплохо"},
            headers=bearer(emp_token),
        )
        assert resp.status_code == 201
        data = resp.json()
        for field in ("id", "order_id", "author_id", "recipient_id", "rating", "text", "created_at"):
            assert field in data, f"Missing field: {field}"

    def test_author_id_matches_requester(self, client, db, profession):
        order_id, emp_token, _ = _setup_completed_order(client, db, profession)
        emp_id = str(get_user_id(client, emp_token))
        resp = client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 5},
            headers=bearer(emp_token),
        )
        assert resp.json()["author_id"] == emp_id

    def test_recipient_is_opposite_participant(self, client, db, profession):
        order_id, emp_token, wrk_token = _setup_completed_order(client, db, profession)
        wrk_id = str(get_user_id(client, wrk_token))
        resp = client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 5},
            headers=bearer(emp_token),
        )
        assert resp.json()["recipient_id"] == wrk_id

    def test_text_none_allowed(self, client, db, profession):
        order_id, emp_token, _ = _setup_completed_order(client, db, profession)
        resp = client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 4},
            headers=bearer(emp_token),
        )
        assert resp.status_code == 201
        assert resp.json()["text"] is None

    def test_whitespace_text_stored_as_none(self, client, db, profession):
        order_id, emp_token, _ = _setup_completed_order(client, db, profession)
        resp = client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 4, "text": "   "},
            headers=bearer(emp_token),
        )
        assert resp.status_code == 201
        assert resp.json()["text"] is None

    def test_rating_min_1(self, client, db, profession):
        order_id, emp_token, _ = _setup_completed_order(client, db, profession)
        resp = client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 1},
            headers=bearer(emp_token),
        )
        assert resp.status_code == 201
        assert resp.json()["rating"] == 1

    def test_rating_max_5(self, client, db, profession):
        order_id, emp_token, _ = _setup_completed_order(client, db, profession)
        resp = client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 5},
            headers=bearer(emp_token),
        )
        assert resp.status_code == 201
        assert resp.json()["rating"] == 5

    def test_rating_below_1_rejected(self, client, db, profession):
        order_id, emp_token, _ = _setup_completed_order(client, db, profession)
        resp = client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 0},
            headers=bearer(emp_token),
        )
        assert resp.status_code == 422

    def test_rating_above_5_rejected(self, client, db, profession):
        order_id, emp_token, _ = _setup_completed_order(client, db, profession)
        resp = client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 6},
            headers=bearer(emp_token),
        )
        assert resp.status_code == 422

    def test_nonexistent_order_returns_404(self, client, profession):
        _, token = _register(client, "employer")
        resp = client.post(
            "/reviews/",
            json={"order_id": str(uuid.uuid4()), "rating": 5},
            headers=bearer(token),
        )
        assert resp.status_code == 404

    def test_order_not_completed_returns_409(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        _, wrk_token = _register(client, "worker")
        make_worker_profile(db, get_user_id(client, wrk_token), profession)

        create_resp = client.post(
            "/orders/",
            json=_order_payload(profession),
            headers=bearer(emp_token),
        )
        offer_id = create_resp.json()["active_offer_id"]
        client.post(
            f"/orders/offers/{offer_id}/respond",
            json={"accept": True},
            headers=bearer(wrk_token),
        )
        order_id = create_resp.json()["order"]["id"]

        resp = client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 5},
            headers=bearer(emp_token),
        )
        assert resp.status_code == 409

    def test_pending_order_returns_409(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        _, wrk_token = _register(client, "worker")
        make_worker_profile(db, get_user_id(client, wrk_token), profession)

        create_resp = client.post(
            "/orders/",
            json=_order_payload(profession),
            headers=bearer(emp_token),
        )
        order_id = create_resp.json()["order"]["id"]

        resp = client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 5},
            headers=bearer(emp_token),
        )
        assert resp.status_code == 409

    def test_non_participant_forbidden(self, client, db, profession):
        order_id, _, _ = _setup_completed_order(client, db, profession)
        _, stranger_token = _register(client, "employer")
        resp = client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 5},
            headers=bearer(stranger_token),
        )
        assert resp.status_code == 403

    def test_duplicate_review_rejected(self, client, db, profession):
        order_id, emp_token, _ = _setup_completed_order(client, db, profession)
        client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 5},
            headers=bearer(emp_token),
        )
        resp = client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 3},
            headers=bearer(emp_token),
        )
        assert resp.status_code == 409

    def test_unauthenticated_rejected(self, client, profession):
        resp = client.post("/reviews/", json={"order_id": str(uuid.uuid4()), "rating": 5})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /reviews/received
# ---------------------------------------------------------------------------

class TestGetReceivedReviews:

    def test_returns_list(self, client, db, profession):
        order_id, emp_token, wrk_token = _setup_completed_order(client, db, profession)
        client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 4, "text": "Хорошо"},
            headers=bearer(emp_token),
        )
        resp = client.get("/reviews/received", headers=bearer(wrk_token))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_contains_review_sent_to_me(self, client, db, profession):
        order_id, emp_token, wrk_token = _setup_completed_order(client, db, profession)
        wrk_id = str(get_user_id(client, wrk_token))
        client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 5},
            headers=bearer(emp_token),
        )
        resp = client.get("/reviews/received", headers=bearer(wrk_token))
        assert any(r["recipient_id"] == wrk_id for r in resp.json())

    def test_empty_when_no_reviews(self, client, profession):
        _, token = _register(client, "worker")
        resp = client.get("/reviews/received", headers=bearer(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_does_not_include_given_reviews(self, client, db, profession):
        order_id, emp_token, wrk_token = _setup_completed_order(client, db, profession)
        emp_id = str(get_user_id(client, emp_token))
        # Работник оставляет отзыв работодателю
        client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 5},
            headers=bearer(wrk_token),
        )
        # В /received работника не должно быть отзывов, которые он сам написал
        resp = client.get("/reviews/received", headers=bearer(wrk_token))
        assert all(r["author_id"] != str(get_user_id(client, wrk_token)) for r in resp.json())

    def test_unauthenticated_rejected(self, client):
        resp = client.get("/reviews/received")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /reviews/given
# ---------------------------------------------------------------------------

class TestGetGivenReviews:

    def test_returns_list(self, client, db, profession):
        order_id, emp_token, _ = _setup_completed_order(client, db, profession)
        client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 5},
            headers=bearer(emp_token),
        )
        resp = client.get("/reviews/given", headers=bearer(emp_token))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_contains_review_i_wrote(self, client, db, profession):
        order_id, emp_token, _ = _setup_completed_order(client, db, profession)
        emp_id = str(get_user_id(client, emp_token))
        client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 5},
            headers=bearer(emp_token),
        )
        resp = client.get("/reviews/given", headers=bearer(emp_token))
        assert any(r["author_id"] == emp_id for r in resp.json())

    def test_empty_when_no_reviews(self, client, profession):
        _, token = _register(client, "employer")
        resp = client.get("/reviews/given", headers=bearer(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_does_not_include_received_reviews(self, client, db, profession):
        order_id, emp_token, wrk_token = _setup_completed_order(client, db, profession)
        emp_id = str(get_user_id(client, emp_token))
        # Работник оставляет отзыв работодателю
        client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 5},
            headers=bearer(wrk_token),
        )
        # В /given работодателя не должно быть отзыва воркера (он получатель, не автор)
        resp = client.get("/reviews/given", headers=bearer(emp_token))
        assert all(r["author_id"] == emp_id for r in resp.json())

    def test_unauthenticated_rejected(self, client):
        resp = client.get("/reviews/given")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /reviews/by-order/{order_id}
# ---------------------------------------------------------------------------

class TestGetReviewsByOrder:

    def test_employer_can_see_reviews(self, client, db, profession):
        order_id, emp_token, wrk_token = _setup_completed_order(client, db, profession)
        client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 5},
            headers=bearer(emp_token),
        )
        resp = client.get(f"/reviews/by-order/{order_id}", headers=bearer(emp_token))
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_worker_can_see_reviews(self, client, db, profession):
        order_id, emp_token, wrk_token = _setup_completed_order(client, db, profession)
        client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 5},
            headers=bearer(emp_token),
        )
        resp = client.get(f"/reviews/by-order/{order_id}", headers=bearer(wrk_token))
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_both_reviews_visible(self, client, db, profession):
        order_id, emp_token, wrk_token = _setup_completed_order(client, db, profession)
        client.post("/reviews/", json={"order_id": order_id, "rating": 5}, headers=bearer(emp_token))
        client.post("/reviews/", json={"order_id": order_id, "rating": 4}, headers=bearer(wrk_token))

        resp = client.get(f"/reviews/by-order/{order_id}", headers=bearer(emp_token))
        assert len(resp.json()) == 2

    def test_non_participant_forbidden(self, client, db, profession):
        order_id, _, _ = _setup_completed_order(client, db, profession)
        _, stranger_token = _register(client, "employer")
        resp = client.get(f"/reviews/by-order/{order_id}", headers=bearer(stranger_token))
        assert resp.status_code == 403

    def test_nonexistent_order_returns_404(self, client, profession):
        _, token = _register(client, "employer")
        resp = client.get(f"/reviews/by-order/{uuid.uuid4()}", headers=bearer(token))
        assert resp.status_code == 404

    def test_unauthenticated_rejected(self, client, profession):
        resp = client.get(f"/reviews/by-order/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Бизнес-логика: пересчёт рейтинга воркера
# ---------------------------------------------------------------------------

class TestWorkerRatingRecalculation:

    def test_rating_avg_updated_after_review(self, client, db, profession):
        order_id, emp_token, wrk_token = _setup_completed_order(client, db, profession)
        wrk_id = get_user_id(client, wrk_token)

        client.post(
            "/reviews/",
            json={"order_id": order_id, "rating": 4},
            headers=bearer(emp_token),
        )

        profile = client.get("/workers/me/profile", headers=bearer(wrk_token)).json()
        assert float(profile["rating_avg"]) == 4.0
        assert profile["reviews_count"] == 1

    def test_rating_avg_is_mean_of_all_reviews(self, client, db, profession):
        # Первый заказ
        order1_id, emp1_token, wrk_token = _setup_completed_order(client, db, profession)
        client.post("/reviews/", json={"order_id": order1_id, "rating": 2}, headers=bearer(emp1_token))

        # Второй заказ с тем же воркером
        _, emp2_token = _register(client, "employer")
        create_resp = client.post(
            "/orders/",
            json=_order_payload(profession),
            headers=bearer(emp2_token),
        )
        order2_id = create_resp.json()["order"]["id"]
        offer2_id = create_resp.json()["active_offer_id"]
        client.post(f"/orders/offers/{offer2_id}/respond", json={"accept": True}, headers=bearer(wrk_token))
        client.patch(f"/orders/{order2_id}/complete", headers=bearer(emp2_token))
        client.post("/reviews/", json={"order_id": order2_id, "rating": 4}, headers=bearer(emp2_token))

        profile = client.get("/workers/me/profile", headers=bearer(wrk_token)).json()
        assert float(profile["rating_avg"]) == 3.0
        assert profile["reviews_count"] == 2

    def test_employer_review_does_not_affect_worker_rating(self, client, db, profession):
        order_id, emp_token, wrk_token = _setup_completed_order(client, db, profession)
        # Воркер оценивает работодателя — рейтинг воркера не должен измениться
        client.post("/reviews/", json={"order_id": order_id, "rating": 1}, headers=bearer(wrk_token))

        profile = client.get("/workers/me/profile", headers=bearer(wrk_token)).json()
        assert float(profile["rating_avg"]) == 0.0
        assert profile["reviews_count"] == 0
