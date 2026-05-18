import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from services.auth_service import login_user, register_user

_SVC = "services.auth_service"


def fake_user(email="user@example.com", is_active=True):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = email
    u.is_active = is_active
    u.password_hash = "hashed_pw"
    return u


@contextmanager
def patch_register(user=None, pw_hash="h", token="tok", ttl=3600):
    user = user or fake_user()
    with (
        patch(f"{_SVC}.get_user_by_email", return_value=None) as m_email,
        patch(f"{_SVC}.get_user_by_phone", return_value=None),
        patch(f"{_SVC}.create_user", return_value=user) as m_create,
        patch(f"{_SVC}.get_password_hash", return_value=pw_hash) as m_hash,
        patch(f"{_SVC}.create_access_token", return_value=token),
        patch(f"{_SVC}.access_token_ttl_seconds", return_value=ttl),
    ):
        yield {"user": user, "email": m_email, "create": m_create, "hash": m_hash}


def reg(**overrides):
    base = dict(email="test@example.com", password="secret123",
                last_name="Иванов", first_name="Иван", patronymic=None, role="worker")
    return {**base, **overrides}


class TestRegisterUser:

    def test_success(self):
        with patch_register(token="jwt_token", ttl=3600):
            result = register_user(MagicMock(), **reg())

        assert result.access_token == "jwt_token"
        assert result.token_type == "bearer"
        assert result.expires_in == 3600

    def test_password_is_hashed_not_stored_raw(self):
        with patch_register(pw_hash="bcrypt_result") as m:
            register_user(MagicMock(), **reg(password="plaintext"))

        m["hash"].assert_called_once_with("plaintext")
        _, kwargs = m["create"].call_args
        assert kwargs["password_hash"] == "bcrypt_result"

    @patch(f"{_SVC}.get_user_by_email")
    def test_duplicate_email(self, mock_email):
        mock_email.return_value = fake_user()

        with pytest.raises(HTTPException) as exc:
            register_user(MagicMock(), **reg(email="dup@example.com"))

        assert exc.value.status_code == 409
        assert "Email already registered" in exc.value.detail

    @patch(f"{_SVC}.get_user_by_phone")
    @patch(f"{_SVC}.get_user_by_email", return_value=None)
    def test_duplicate_phone(self, _email, mock_phone):
        mock_phone.return_value = fake_user()

        with pytest.raises(HTTPException) as exc:
            register_user(MagicMock(), **reg(phone="+79990001122"))

        assert exc.value.status_code == 409
        assert "Phone already registered" in exc.value.detail

    def test_email_lowercased_before_lookup(self):
        db = MagicMock()
        with patch_register() as m:
            register_user(db, **reg(email="  USER@EXAMPLE.COM  "))

        m["email"].assert_called_once_with(db, "user@example.com")

    def test_blank_patronymic_saved_as_none(self):
        with patch_register() as m:
            register_user(MagicMock(), **reg(patronymic="   "))

        _, kwargs = m["create"].call_args
        assert kwargs["patronymic"] is None

    def test_photo_url_stripped(self):
        with patch_register() as m:
            register_user(MagicMock(), **reg(photo_url="  https://cdn.example.com/photo.jpg  "))

        _, kwargs = m["create"].call_args
        assert kwargs["photo_url"] == "https://cdn.example.com/photo.jpg"

    def test_blank_photo_url_becomes_none(self):
        with patch_register() as m:
            register_user(MagicMock(), **reg(photo_url="   "))

        _, kwargs = m["create"].call_args
        assert kwargs["photo_url"] is None


class TestLoginUser:

    @patch(f"{_SVC}.access_token_ttl_seconds", return_value=3600)
    @patch(f"{_SVC}.create_access_token", return_value="jwt_token")
    @patch(f"{_SVC}.verify_password", return_value=True)
    @patch(f"{_SVC}.get_user_by_email")
    def test_success(self, mock_email, mock_verify, _token, _ttl):
        user = fake_user()
        mock_email.return_value = user

        result = login_user(MagicMock(), "user@example.com", "secret123")

        assert result.access_token == "jwt_token"
        mock_verify.assert_called_once_with("secret123", user.password_hash)

    @patch(f"{_SVC}.verify_password", return_value=False)
    @patch(f"{_SVC}.get_user_by_email")
    def test_wrong_password(self, mock_email, _verify):
        mock_email.return_value = fake_user()

        with pytest.raises(HTTPException) as exc:
            login_user(MagicMock(), "user@example.com", "wrong")

        assert exc.value.status_code == 401
        assert "Invalid email or password" in exc.value.detail

    @patch(f"{_SVC}.get_user_by_email", return_value=None)
    def test_unknown_email(self, _email):
        with pytest.raises(HTTPException) as exc:
            login_user(MagicMock(), "nobody@example.com", "secret123")

        assert exc.value.status_code == 401

    @patch(f"{_SVC}.verify_password", return_value=True)
    @patch(f"{_SVC}.get_user_by_email")
    def test_inactive_user(self, mock_email, _verify):
        mock_email.return_value = fake_user(is_active=False)

        with pytest.raises(HTTPException) as exc:
            login_user(MagicMock(), "user@example.com", "secret123")

        assert exc.value.status_code == 403
        assert "inactive" in exc.value.detail.lower()

    @patch(f"{_SVC}.access_token_ttl_seconds", return_value=3600)
    @patch(f"{_SVC}.create_access_token", return_value="t")
    @patch(f"{_SVC}.verify_password", return_value=True)
    @patch(f"{_SVC}.get_user_by_email")
    def test_email_lowercased_before_lookup(self, mock_email, _verify, _token, _ttl):
        mock_email.return_value = fake_user()
        db = MagicMock()

        login_user(db, "  USER@EXAMPLE.COM  ", "secret123")

        mock_email.assert_called_once_with(db, "user@example.com")
