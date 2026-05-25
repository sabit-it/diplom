"""
Интеграционные тесты для GET /workers/ (каталог исполнителей).
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


def unique_email() -> str:
    return f"cat_{uuid.uuid4().hex[:12]}@example.com"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, role: str) -> tuple[dict, str]:
    payload = {
        "email": unique_email(),
        "password": "secret12345",
        "last_name": "Каталог",
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
    rating_avg: Decimal = Decimal("0.00"),
    is_online: bool = True,
    lat: str = "55.751244",
    lng: str = "37.618423",
) -> WorkerProfile:
    wp = WorkerProfile(
        user_id=user_id,
        profession_id=profession_id,
        is_online=is_online,
        rating_avg=rating_avg,
        current_lat=Decimal(lat),
        current_lng=Decimal(lng),
    )
    db.add(wp)
    db.commit()
    db.refresh(wp)
    return wp


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
        id=31001,
        name=f"КатТест_{uuid.uuid4().hex[:8]}",
        hourly_rate=Decimal("500.00"),
        rate_unit="hour",
        is_active=True,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


@pytest.fixture()
def profession2(db: Session) -> int:
    p = Profession(
        id=31002,
        name=f"КатТест2_{uuid.uuid4().hex[:8]}",
        hourly_rate=Decimal("700.00"),
        rate_unit="hour",
        is_active=True,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


class TestWorkersCatalog:

    def test_returns_empty_list(self, client, db, profession):
        _, token = _register(client, "employer")
        resp = client.get("/workers/", headers=bearer(token))
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    def test_returns_worker_with_profile(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        _, wrk_token = _register(client, "worker")
        wrk_id = get_user_id(client, wrk_token)
        make_worker_profile(db, wrk_id, profession)

        resp = client.get("/workers/", headers=bearer(emp_token))
        assert resp.status_code == 200
        items = resp.json()["items"]
        worker_ids = [i["user_id"] for i in items]
        assert str(wrk_id) in worker_ids

    def test_response_has_required_fields(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        _, wrk_token = _register(client, "worker")
        wrk_id = get_user_id(client, wrk_token)
        make_worker_profile(db, wrk_id, profession)

        resp = client.get("/workers/", headers=bearer(emp_token))
        item = resp.json()["items"][0]
        for field in ("id", "user_id", "first_name", "last_name", "profession",
                      "rating_avg", "reviews_count", "completed_orders", "is_online"):
            assert field in item, f"Missing field: {field}"

    def test_filter_by_profession(self, client, db, profession, profession2):
        _, emp_token = _register(client, "employer")
        _, wrk1_token = _register(client, "worker")
        _, wrk2_token = _register(client, "worker")
        make_worker_profile(db, get_user_id(client, wrk1_token), profession)
        make_worker_profile(db, get_user_id(client, wrk2_token), profession2)

        resp = client.get("/workers/", params={"profession_id": profession}, headers=bearer(emp_token))
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(i["profession"]["id"] == profession for i in items)

    def test_filter_is_online_true(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        _, online_token = _register(client, "worker")
        _, offline_token = _register(client, "worker")
        online_id = get_user_id(client, online_token)
        offline_id = get_user_id(client, offline_token)
        make_worker_profile(db, online_id, profession, is_online=True)
        make_worker_profile(db, offline_id, profession, is_online=False)

        resp = client.get("/workers/", params={"is_online": "true"}, headers=bearer(emp_token))
        ids = [i["user_id"] for i in resp.json()["items"]]
        assert str(online_id) in ids
        assert str(offline_id) not in ids

    def test_filter_min_rating(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        _, high_token = _register(client, "worker")
        _, low_token = _register(client, "worker")
        high_id = get_user_id(client, high_token)
        low_id = get_user_id(client, low_token)
        make_worker_profile(db, high_id, profession, rating_avg=Decimal("4.50"))
        make_worker_profile(db, low_id, profession, rating_avg=Decimal("2.00"))

        resp = client.get("/workers/", params={"min_rating": 4.0}, headers=bearer(emp_token))
        ids = [i["user_id"] for i in resp.json()["items"]]
        assert str(high_id) in ids
        assert str(low_id) not in ids

    def test_pagination_limit_offset(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        for _ in range(3):
            _, wrk_token = _register(client, "worker")
            make_worker_profile(db, get_user_id(client, wrk_token), profession)

        resp1 = client.get("/workers/", params={"limit": 2, "offset": 0}, headers=bearer(emp_token))
        resp2 = client.get("/workers/", params={"limit": 2, "offset": 2}, headers=bearer(emp_token))

        data1 = resp1.json()
        data2 = resp2.json()
        assert len(data1["items"]) == 2
        assert data1["total"] >= 3

        ids1 = {i["id"] for i in data1["items"]}
        ids2 = {i["id"] for i in data2["items"]}
        assert ids1.isdisjoint(ids2)

    def test_unauthenticated_rejected(self, client, db, profession):
        resp = client.get("/workers/")
        assert resp.status_code == 401

    def test_sorted_by_rating_desc(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        for rating in [Decimal("3.00"), Decimal("5.00"), Decimal("1.00")]:
            _, wrk_token = _register(client, "worker")
            make_worker_profile(db, get_user_id(client, wrk_token), profession, rating_avg=rating)

        resp = client.get("/workers/", params={"profession_id": profession}, headers=bearer(emp_token))
        ratings = [float(i["rating_avg"]) for i in resp.json()["items"]]
        assert ratings == sorted(ratings, reverse=True)


class TestWorkersCatalogGeo:
    """Тесты режима гео-поиска: GET /workers/?lat=...&lng=..."""

    # Центр поиска — Москва, Красная площадь
    SEARCH_LAT = "55.7539"
    SEARCH_LNG = "37.6208"

    # ~500 м от центра
    NEAR_LAT = "55.7500"
    NEAR_LNG = "37.6208"

    # ~50 км от центра (Солнечногорск)
    FAR_LAT = "56.1852"
    FAR_LNG = "36.9877"

    def test_geo_returns_distance_meters(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        _, wrk_token = _register(client, "worker")
        make_worker_profile(db, get_user_id(client, wrk_token), profession,
                            lat=self.NEAR_LAT, lng=self.NEAR_LNG)

        resp = client.get("/workers/", params={
            "lat": self.SEARCH_LAT, "lng": self.SEARCH_LNG,
            "profession_id": profession,
        }, headers=bearer(emp_token))
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        assert items[0]["distance_meters"] is not None
        assert items[0]["distance_meters"] > 0

    def test_geo_sorted_nearest_first(self, client, db, profession):
        _, emp_token = _register(client, "employer")

        _, near_token = _register(client, "worker")
        _, far_token = _register(client, "worker")
        make_worker_profile(db, get_user_id(client, near_token), profession,
                            lat=self.NEAR_LAT, lng=self.NEAR_LNG)
        make_worker_profile(db, get_user_id(client, far_token), profession,
                            lat=self.FAR_LAT, lng=self.FAR_LNG)

        resp = client.get("/workers/", params={
            "lat": self.SEARCH_LAT, "lng": self.SEARCH_LNG,
            "profession_id": profession,
        }, headers=bearer(emp_token))
        items = resp.json()["items"]
        near_id = str(get_user_id(client, near_token))
        far_id = str(get_user_id(client, far_token))

        user_ids = [i["user_id"] for i in items]
        assert user_ids.index(near_id) < user_ids.index(far_id)

    def test_geo_distances_ascending(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        for lat in [self.NEAR_LAT, self.FAR_LAT]:
            _, wrk_token = _register(client, "worker")
            make_worker_profile(db, get_user_id(client, wrk_token), profession,
                                lat=lat, lng=self.SEARCH_LNG)

        resp = client.get("/workers/", params={
            "lat": self.SEARCH_LAT, "lng": self.SEARCH_LNG,
            "profession_id": profession,
        }, headers=bearer(emp_token))
        distances = [i["distance_meters"] for i in resp.json()["items"]]
        assert distances == sorted(distances)

    def test_geo_max_distance_filters(self, client, db, profession):
        _, emp_token = _register(client, "employer")

        _, near_token = _register(client, "worker")
        _, far_token = _register(client, "worker")
        make_worker_profile(db, get_user_id(client, near_token), profession,
                            lat=self.NEAR_LAT, lng=self.NEAR_LNG)
        make_worker_profile(db, get_user_id(client, far_token), profession,
                            lat=self.FAR_LAT, lng=self.FAR_LNG)

        # Радиус 5 км — ближний попадает, дальний нет
        resp = client.get("/workers/", params={
            "lat": self.SEARCH_LAT, "lng": self.SEARCH_LNG,
            "profession_id": profession,
            "max_distance_km": 5,
        }, headers=bearer(emp_token))
        user_ids = [i["user_id"] for i in resp.json()["items"]]
        near_id = str(get_user_id(client, near_token))
        far_id = str(get_user_id(client, far_token))
        assert near_id in user_ids
        assert far_id not in user_ids

    def test_geo_workers_without_coords_excluded(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        _, wrk_token = _register(client, "worker")
        # Профиль без координат
        wp = WorkerProfile(
            user_id=get_user_id(client, wrk_token),
            profession_id=profession,
            is_online=True,
        )
        db.add(wp)
        db.commit()

        resp = client.get("/workers/", params={
            "lat": self.SEARCH_LAT, "lng": self.SEARCH_LNG,
            "profession_id": profession,
        }, headers=bearer(emp_token))
        user_ids = [i["user_id"] for i in resp.json()["items"]]
        assert str(get_user_id(client, wrk_token)) not in user_ids

    def test_geo_only_lat_returns_422(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        resp = client.get("/workers/", params={"lat": self.SEARCH_LAT}, headers=bearer(emp_token))
        assert resp.status_code == 422

    def test_geo_only_lng_returns_422(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        resp = client.get("/workers/", params={"lng": self.SEARCH_LNG}, headers=bearer(emp_token))
        assert resp.status_code == 422

    def test_no_geo_distance_meters_is_none(self, client, db, profession):
        _, emp_token = _register(client, "employer")
        _, wrk_token = _register(client, "worker")
        make_worker_profile(db, get_user_id(client, wrk_token), profession)

        resp = client.get("/workers/", params={"profession_id": profession}, headers=bearer(emp_token))
        items = resp.json()["items"]
        assert len(items) >= 1
        assert items[0]["distance_meters"] is None
