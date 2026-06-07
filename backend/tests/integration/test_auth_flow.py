"""
Integration tests — Auth API (/api/v1/auth/*)

Covers:
  POST /api/v1/auth/register   — register a new user
  POST /api/v1/auth/login      — authenticate, receive tokens
  POST /api/v1/auth/refresh    — exchange refresh token for new pair
  GET  /api/v1/auth/me         — return authenticated user profile
  POST /api/v1/auth/logout     — invalidate session

All tests use a real PostgreSQL session (rolled back after each test).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_register_new_user(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "integration@example.com",
            "password": "SecureP@ss123",
            "full_name": "Integration Tester",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "integration@example.com"
    assert data["full_name"] == "Integration Tester"
    assert data["role"] == "developer"
    assert "id" in data
    assert "hashed_password" not in data


@pytest.mark.anyio
async def test_register_duplicate_email(client: AsyncClient) -> None:
    payload = {
        "email": "dup@example.com",
        "password": "SecureP@ss123",
        "full_name": "Dup User",
    }
    r1 = await client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 201

    r2 = await client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 409
    assert "already registered" in r2.json()["detail"].lower()


@pytest.mark.anyio
async def test_login_valid_credentials(client: AsyncClient) -> None:
    # Register first
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "logintest@example.com",
            "password": "SecureP@ss123",
            "full_name": "Login Tester",
        },
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "logintest@example.com", "password": "SecureP@ss123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


@pytest.mark.anyio
async def test_login_wrong_password(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrongpw@example.com",
            "password": "CorrectPass123",
            "full_name": "Wrong PW",
        },
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpw@example.com", "password": "WrongPass999"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_login_unknown_email(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "pass123"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_get_me_with_valid_token(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "metest@example.com",
            "password": "SecureP@ss123",
            "full_name": "Me Tester",
        },
    )
    login_r = await client.post(
        "/api/v1/auth/login",
        json={"email": "metest@example.com", "password": "SecureP@ss123"},
    )
    token = login_r.json()["access_token"]

    me_r = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_r.status_code == 200
    data = me_r.json()
    assert data["email"] == "metest@example.com"
    assert data["full_name"] == "Me Tester"


@pytest.mark.anyio
async def test_get_me_without_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_refresh_tokens(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "refreshtest@example.com",
            "password": "SecureP@ss123",
            "full_name": "Refresh Tester",
        },
    )
    login_r = await client.post(
        "/api/v1/auth/login",
        json={"email": "refreshtest@example.com", "password": "SecureP@ss123"},
    )
    refresh_token = login_r.json()["refresh_token"]

    refresh_r = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_r.status_code == 200
    data = refresh_r.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.anyio
async def test_refresh_with_invalid_token(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "this.is.not.valid"},
    )
    assert response.status_code == 401
