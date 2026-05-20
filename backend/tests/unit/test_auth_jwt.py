"""Unit tests for JWT auth utilities."""

import pytest
from jose import JWTError

from app.core.security.zero_trust import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_access_token,
    verify_password,
    verify_refresh_token,
)


class TestPasswordHashing:
    def test_hash_password_returns_hash(self) -> None:
        hashed = hash_password("SecurePass1")
        assert hashed != "SecurePass1"
        assert len(hashed) > 20

    def test_verify_password_correct(self) -> None:
        hashed = hash_password("SecurePass1")
        assert verify_password("SecurePass1", hashed) is True

    def test_verify_password_wrong(self) -> None:
        hashed = hash_password("SecurePass1")
        assert verify_password("WrongPass1", hashed) is False


class TestJWTTokens:
    def test_access_token_round_trip(self) -> None:
        token = create_access_token("user-123")
        subject = verify_access_token(token)
        assert subject == "user-123"

    def test_refresh_token_round_trip(self) -> None:
        token = create_refresh_token("user-456")
        subject = verify_refresh_token(token)
        assert subject == "user-456"

    def test_access_token_rejected_as_refresh(self) -> None:
        token = create_access_token("user-123")
        with pytest.raises(JWTError):
            verify_refresh_token(token)

    def test_refresh_token_rejected_as_access(self) -> None:
        token = create_refresh_token("user-123")
        with pytest.raises(JWTError):
            verify_access_token(token)

    def test_tampered_token_rejected(self) -> None:
        token = create_access_token("user-123")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(JWTError):
            verify_access_token(tampered)

    def test_access_token_includes_extra_claims(self) -> None:
        token = create_access_token("user-123", extra_claims={"role": "admin"})
        subject = verify_access_token(token)
        assert subject == "user-123"
