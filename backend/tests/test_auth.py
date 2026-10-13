from uuid import uuid4

from fastapi.testclient import TestClient


def test_register_login_and_get_current_user(client: TestClient):
    email = f"test-{uuid4()}@example.com"
    password = "TestPassword123!"

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Test User",
        },
    )

    assert register_response.status_code == 201

    registered_user = register_response.json()

    assert registered_user["email"] == email
    assert registered_user["full_name"] == "Test User"
    assert "hashed_password" not in registered_user

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )

    assert login_response.status_code == 200

    token = login_response.json()["access_token"]

    me_response = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert me_response.status_code == 200
    assert me_response.json()["email"] == email

    duplicate_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Duplicate User",
        },
    )

    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {
        "detail": "Email is already registered",
    }

    wrong_password_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "WrongPassword123!",
        },
    )

    assert wrong_password_response.status_code == 401
    assert wrong_password_response.json() == {
        "detail": "Invalid email or password",
    }

    invalid_token_response = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": "Bearer invalid-token",
        },
    )

    assert invalid_token_response.status_code == 401
    assert invalid_token_response.json() == {
        "detail": "Could not validate credentials",
    }


def test_register_concurrency_integrity_error_returns_409(client: TestClient, monkeypatch):
    from sqlalchemy.exc import IntegrityError

    import app.services.auth

    async def mock_create_user(*args, **kwargs):
        raise IntegrityError("mock_statement", "mock_params", Exception("duplicate key value"))

    monkeypatch.setattr(app.services.auth, "create_user", mock_create_user)

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"concurrent-{uuid4()}@example.com",
            "password": "Password123!",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Email is already registered",
    }