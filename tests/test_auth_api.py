import uuid

from fastapi.testclient import TestClient


def unique_email():
    return f"test_{uuid.uuid4().hex[:12]}@example.com"


def unique_phone():
    return f"+7999{uuid.uuid4().int % 10_000_000:07d}"


def reg_payload(**overrides):
    base = {
        "email": unique_email(),
        "password": "secret12345",
        "last_name": "Тестов",
        "first_name": "Тест",
        "patronymic": None,
        "role": "worker",
    }
    return {**base, **overrides}


def register(client: TestClient, **overrides):
    payload = reg_payload(**overrides)
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    return payload, resp.json()["access_token"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


class TestRegister:

    def test_success(self, client):
        resp = client.post("/auth/register", json=reg_payload())
        assert resp.status_code == 201
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0

    def test_duplicate_email(self, client):
        email = unique_email()
        client.post("/auth/register", json=reg_payload(email=email))
        resp = client.post("/auth/register", json=reg_payload(email=email))
        assert resp.status_code == 409
        assert "Email already registered" in resp.json()["detail"]

    def test_duplicate_phone(self, client):
        phone = unique_phone()
        client.post("/auth/register", json=reg_payload(phone=phone))
        resp = client.post("/auth/register", json=reg_payload(phone=phone))
        assert resp.status_code == 409
        assert "Phone already registered" in resp.json()["detail"]

    def test_email_case_insensitive(self, client):
        email = unique_email()
        client.post("/auth/register", json=reg_payload(email=email.upper()))
        # тот же email строчными — должен конфликтовать
        resp = client.post("/auth/register", json=reg_payload(email=email))
        assert resp.status_code == 409

    def test_short_password_rejected(self, client):
        resp = client.post("/auth/register", json=reg_payload(password="short"))
        assert resp.status_code == 422

    def test_missing_required_fields(self, client):
        resp = client.post("/auth/register", json={"email": unique_email()})
        assert resp.status_code == 422


class TestLogin:

    def test_json_login(self, client):
        payload, _ = register(client)
        resp = client.post("/auth/login", json={"email": payload["email"], "password": payload["password"]})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_wrong_password(self, client):
        payload, _ = register(client)
        resp = client.post("/auth/login", json={"email": payload["email"], "password": "wrong_pass"})
        assert resp.status_code == 401

    def test_unknown_email(self, client):
        resp = client.post("/auth/login", json={"email": "nobody@example.com", "password": "secret12345"})
        assert resp.status_code == 401

    def test_oauth2_form(self, client):
        payload, _ = register(client)
        resp = client.post("/auth/token", data={"username": payload["email"], "password": payload["password"]})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_oauth2_form_wrong_password(self, client):
        payload, _ = register(client)
        resp = client.post("/auth/token", data={"username": payload["email"], "password": "bad"})
        assert resp.status_code == 401

    def test_register_and_login_tokens_both_work(self, client):
        payload, reg_token = register(client)
        login_token = client.post(
            "/auth/login", json={"email": payload["email"], "password": payload["password"]}
        ).json()["access_token"]

        for token in (reg_token, login_token):
            assert client.get("/auth/me", headers=bearer(token)).status_code == 200


class TestMe:

    def test_returns_profile(self, client):
        payload, token = register(client)
        resp = client.get("/auth/me", headers=bearer(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == payload["email"]
        assert body["role"] == payload["role"]
        assert body["last_name"] == payload["last_name"]

    def test_no_password_in_response(self, client):
        _, token = register(client)
        body = client.get("/auth/me", headers=bearer(token)).json()
        assert "password" not in body
        assert "password_hash" not in body

    def test_no_token(self, client):
        assert client.get("/auth/me").status_code == 401

    def test_invalid_token(self, client):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer garbage.token.here"})
        assert resp.status_code == 401

    def test_malformed_header(self, client):
        resp = client.get("/auth/me", headers={"Authorization": "NotBearer sometoken"})
        assert resp.status_code == 401

    def test_employer_role(self, client):
        _, token = register(client, role="employer")
        assert client.get("/auth/me", headers=bearer(token)).json()["role"] == "employer"


class TestLocation:

    def test_patch_location(self, client):
        _, token = register(client)
        resp = client.patch(
            "/auth/me/location",
            json={"lat": "55.751244", "lng": "37.618423"},
            headers=bearer(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["lat"] is not None
        assert body["lng"] is not None
        assert body["location_updated_at"] is not None

    def test_patch_location_returns_own_profile(self, client):
        payload, token = register(client)
        resp = client.patch(
            "/auth/me/location",
            json={"lat": "48.8566", "lng": "2.3522"},
            headers=bearer(token),
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == payload["email"]

    def test_live_location_returns_204(self, client):
        _, token = register(client)
        resp = client.put(
            "/auth/me/location/live",
            json={"lat": "55.751244", "lng": "37.618423"},
            headers=bearer(token),
        )
        assert resp.status_code == 204
        assert resp.content == b""

    def test_patch_location_unauthorized(self, client):
        resp = client.patch("/auth/me/location", json={"lat": "55.0", "lng": "37.0"})
        assert resp.status_code == 401

    def test_patch_location_out_of_range(self, client):
        _, token = register(client)
        resp = client.patch(
            "/auth/me/location",
            json={"lat": "999.0", "lng": "37.0"},
            headers=bearer(token),
        )
        assert resp.status_code == 422
