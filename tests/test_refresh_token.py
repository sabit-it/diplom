"""
Интеграционные тесты для refresh-токена (POST /auth/refresh).
"""
import uuid

import pytest
from fastapi.testclient import TestClient


def unique_email() -> str:
    return f"rf_{uuid.uuid4().hex[:12]}@example.com"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient) -> dict:
    payload = {
        "email": unique_email(),
        "password": "secret12345",
        "last_name": "Обновление",
        "first_name": "Тест",
        "patronymic": None,
        "role": "employer",
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 201
    return resp.json()


class TestTokenResponse:

    def test_register_returns_refresh_token(self, client, db):
        data = _register(client)
        assert "refresh_token" in data
        assert data["refresh_token"]
        assert "refresh_expires_in" in data
        assert data["refresh_expires_in"] > 0

    def test_login_returns_refresh_token(self, client, db):
        email = unique_email()
        client.post("/auth/register", json={
            "email": email, "password": "secret12345",
            "last_name": "А", "first_name": "Б", "patronymic": None, "role": "worker",
        })
        resp = client.post("/auth/login", json={"email": email, "password": "secret12345"})
        assert resp.status_code == 200
        assert "refresh_token" in resp.json()


class TestRefreshEndpoint:

    def test_valid_refresh_returns_new_tokens(self, client, db):
        data = _register(client)
        old_access = data["access_token"]
        old_refresh = data["refresh_token"]

        resp = client.post("/auth/refresh", json={"refresh_token": old_refresh})
        assert resp.status_code == 200
        new_data = resp.json()
        assert "access_token" in new_data
        assert "refresh_token" in new_data
        assert new_data["access_token"] != old_access

    def test_new_access_token_works(self, client, db):
        data = _register(client)
        resp = client.post("/auth/refresh", json={"refresh_token": data["refresh_token"]})
        new_access = resp.json()["access_token"]
        me = client.get("/auth/me", headers=bearer(new_access))
        assert me.status_code == 200

    def test_invalid_token_rejected(self, client, db):
        resp = client.post("/auth/refresh", json={"refresh_token": "not.a.token"})
        assert resp.status_code == 401

    def test_access_token_as_refresh_rejected(self, client, db):
        data = _register(client)
        resp = client.post("/auth/refresh", json={"refresh_token": data["access_token"]})
        assert resp.status_code == 401

    def test_empty_token_rejected(self, client, db):
        resp = client.post("/auth/refresh", json={"refresh_token": ""})
        assert resp.status_code in (401, 422)

    def test_missing_token_rejected(self, client, db):
        resp = client.post("/auth/refresh", json={})
        assert resp.status_code == 422
