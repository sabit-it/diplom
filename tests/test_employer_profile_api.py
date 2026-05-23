"""
Интеграционные тесты для GET/PUT /employers/me (профиль заказчика).
"""
import uuid

import pytest
from fastapi.testclient import TestClient


def unique_email() -> str:
    return f"emp_{uuid.uuid4().hex[:12]}@example.com"


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


class TestGetEmployerProfile:

    def test_returns_404_if_not_created(self, client, db):
        _, token = _register(client, "employer")
        resp = client.get("/employers/me", headers=bearer(token))
        assert resp.status_code == 404

    def test_worker_cannot_access(self, client, db):
        _, token = _register(client, "worker")
        resp = client.get("/employers/me", headers=bearer(token))
        assert resp.status_code == 403

    def test_unauthenticated_rejected(self, client, db):
        resp = client.get("/employers/me")
        assert resp.status_code == 401

    def test_returns_profile_after_creation(self, client, db):
        _, token = _register(client, "employer")
        client.put("/employers/me", json={"company_name": "ООО Тест"}, headers=bearer(token))
        resp = client.get("/employers/me", headers=bearer(token))
        assert resp.status_code == 200
        assert resp.json()["company_name"] == "ООО Тест"


class TestPutEmployerProfile:

    def test_creates_profile(self, client, db):
        _, token = _register(client, "employer")
        resp = client.put(
            "/employers/me",
            json={"company_name": "ООО Ромашка", "address": "Москва, ул. Лесная, 5"},
            headers=bearer(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["company_name"] == "ООО Ромашка"
        assert data["address"] == "Москва, ул. Лесная, 5"

    def test_updates_existing_profile(self, client, db):
        _, token = _register(client, "employer")
        client.put("/employers/me", json={"company_name": "Старое"}, headers=bearer(token))
        resp = client.put("/employers/me", json={"company_name": "Новое"}, headers=bearer(token))
        assert resp.status_code == 200
        assert resp.json()["company_name"] == "Новое"

    def test_null_clears_field(self, client, db):
        _, token = _register(client, "employer")
        client.put("/employers/me", json={"company_name": "ООО Тест"}, headers=bearer(token))
        resp = client.put("/employers/me", json={"company_name": None}, headers=bearer(token))
        assert resp.status_code == 200
        assert resp.json()["company_name"] is None

    def test_empty_string_clears_field(self, client, db):
        _, token = _register(client, "employer")
        client.put("/employers/me", json={"company_name": "ООО Тест"}, headers=bearer(token))
        resp = client.put("/employers/me", json={"company_name": ""}, headers=bearer(token))
        assert resp.status_code == 200
        assert resp.json()["company_name"] is None

    def test_both_fields_optional(self, client, db):
        _, token = _register(client, "employer")
        resp = client.put("/employers/me", json={}, headers=bearer(token))
        assert resp.status_code == 200
        assert resp.json()["company_name"] is None
        assert resp.json()["address"] is None

    def test_worker_cannot_create_profile(self, client, db):
        _, token = _register(client, "worker")
        resp = client.put("/employers/me", json={"company_name": "Hack"}, headers=bearer(token))
        assert resp.status_code == 403

    def test_unauthenticated_rejected(self, client, db):
        resp = client.put("/employers/me", json={"company_name": "Hack"})
        assert resp.status_code == 401

    def test_response_has_required_fields(self, client, db):
        _, token = _register(client, "employer")
        resp = client.put("/employers/me", json={"company_name": "ООО Тест"}, headers=bearer(token))
        data = resp.json()
        for field in ("id", "user_id", "company_name", "address", "created_at", "updated_at"):
            assert field in data, f"Missing field: {field}"

    def test_whitespace_trimmed(self, client, db):
        _, token = _register(client, "employer")
        resp = client.put("/employers/me", json={"company_name": "  ООО Тест  "}, headers=bearer(token))
        assert resp.status_code == 200
        assert resp.json()["company_name"] == "ООО Тест"
