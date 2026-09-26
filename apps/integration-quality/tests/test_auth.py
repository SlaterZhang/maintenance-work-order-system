"""D-API-01/02：登录换 JWT 与当前用户权限上下文"""
from src.config import settings

PASSWORD = settings.login_default_password


def _login(client, username="USER-C-002", password=PASSWORD):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"X-Trace-Id": "trace-d-auth-0001"},
    )


# ---------- D-API-01 登录 ----------
def test_login_success_returns_token_and_user(client):
    r = _login(client, "USER-C-002")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tokenType"] == "Bearer"
    assert data["accessToken"].count(".") == 2
    assert data["expiresInSeconds"] >= 60
    assert data["user"]["userId"] == "USER-C-002"
    assert "WORK_ORDER_MAINTAIN" in data["user"]["permissions"]


def test_login_wrong_password_401(client):
    r = _login(client, "USER-C-002", "wrong-password")
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHORIZED"


def test_login_unknown_user_401(client):
    r = _login(client, "USER-X-999")
    assert r.status_code == 401


def test_login_short_username_400(client):
    r = _login(client, "ab")
    assert r.status_code == 400
    assert r.json()["code"] == "BAD_REQUEST"


# ---------- D-API-02 当前用户上下文 ----------
def test_me_access_context_with_bearer(client):
    token = _login(client, "USER-D-001").json()["accessToken"]
    r = client.get(
        "/api/v1/users/me/access-context",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["userId"] == "USER-D-001"
    assert "ADMIN_ALL" in data["permissions"]


def test_me_access_context_without_token_401(client):
    r = client.get("/api/v1/users/me/access-context")
    assert r.status_code == 401


def test_me_access_context_invalid_token_401(client):
    r = client.get(
        "/api/v1/users/me/access-context",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHORIZED"
