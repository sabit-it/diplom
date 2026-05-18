import time
import uuid

import pytest

from core.security import (
    TokenValidationError,
    access_token_ttl_seconds,
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)


class TestPasswordHashing:
    def test_correct_password_verifies(self):
        h = get_password_hash("my_secure_password")
        assert verify_password("my_secure_password", h) is True

    def test_wrong_password_fails(self):
        h = get_password_hash("correct_password")
        assert verify_password("wrong_password", h) is False

    def test_long_password_over_72_bytes(self):
        # bcrypt обрезает input на 72 байта, но у нас SHA-256 prehash — поэтому длинные пароли работают
        long_pw = "a" * 100
        h = get_password_hash(long_pw)
        assert verify_password(long_pw, h) is True

    def test_empty_password(self):
        h = get_password_hash("")
        assert verify_password("", h) is True

    def test_unicode_password(self):
        pw = "пароль_123_Ω"
        assert verify_password(pw, get_password_hash(pw)) is True

    def test_same_password_hashes_differently_each_time(self):
        h1 = get_password_hash("same_password")
        h2 = get_password_hash("same_password")
        assert h1 != h2

    def test_garbage_hash_string_returns_false(self):
        assert verify_password("password", "not_a_valid_bcrypt_hash") is False


class TestJWT:
    def test_encode_decode_roundtrip(self):
        subject = str(uuid.uuid4())
        token = create_access_token(subject)
        payload = decode_access_token(token)
        assert payload["sub"] == subject

    def test_token_has_future_expiry(self):
        payload = decode_access_token(create_access_token("user"))
        assert payload["exp"] > int(time.time())

    def test_token_has_iat(self):
        payload = decode_access_token(create_access_token("user"))
        assert "iat" in payload

    def test_garbage_token_raises(self):
        with pytest.raises(TokenValidationError):
            decode_access_token("this.is.not.a.valid.jwt")

    def test_tampered_signature_raises(self):
        token = create_access_token("user_id")
        with pytest.raises(TokenValidationError):
            decode_access_token(token[:-4] + "XXXX")

    def test_empty_token_raises(self):
        with pytest.raises(TokenValidationError):
            decode_access_token("")

    def test_ttl_is_positive(self):
        assert access_token_ttl_seconds() > 0
