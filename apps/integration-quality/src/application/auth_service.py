import base64
import hashlib
import hmac
import json
import time

from sqlalchemy.orm import Session

from src.application.identity_service import get_access_context
from src.config import settings
from src.domain.errors import BadRequestError, UnauthorizedError
from src.domain.models import User

_USERNAME_MIN, _USERNAME_MAX = 3, 50
_PASSWORD_MIN, _PASSWORD_MAX = 6, 100


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(signing_input: str) -> str:
    digest = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64url(digest)


def issue_token(user_id: str, role_codes: list[str]) -> tuple[str, int]:
    expires_at = int(time.time()) + settings.jwt_expires_seconds
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "roles": role_codes,
        "iat": int(time.time()),
        "exp": expires_at,
    }
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    )
    return f"{signing_input}.{_sign(signing_input)}", expires_at


def verify_token(token: str) -> str:
    try:
        header_part, payload_part, signature_part = token.split(".")
    except ValueError:
        raise UnauthorizedError("访问令牌格式无效")
    expected = _sign(f"{header_part}.{payload_part}")
    if not hmac.compare_digest(signature_part, expected):
        raise UnauthorizedError("访问令牌签名无效")
    try:
        payload = json.loads(_b64url_decode(payload_part))
    except (ValueError, UnicodeDecodeError):
        raise UnauthorizedError("访问令牌载荷无效")
    if not isinstance(payload.get("sub"), str):
        raise UnauthorizedError("访问令牌缺少用户标识")
    if int(payload.get("exp", 0)) < time.time():
        raise UnauthorizedError("访问令牌已过期")
    return payload["sub"]


def login(db: Session, body: dict) -> dict:
    username = body.get("username")
    password = body.get("password")
    if not isinstance(username, str) or not (
            _USERNAME_MIN <= len(username) <= _USERNAME_MAX):
        raise BadRequestError(
            f"username 长度须在 {_USERNAME_MIN}~{_USERNAME_MAX} 之间")
    if not isinstance(password, str) or not (
            _PASSWORD_MIN <= len(password) <= _PASSWORD_MAX):
        raise BadRequestError(
            f"password 长度须在 {_PASSWORD_MIN}~{_PASSWORD_MAX} 之间")

    user = db.query(User).filter(User.user_id == username).first()
    if user is None or not user.enabled:
        raise UnauthorizedError("用户名或密码错误")
    if password != settings.login_default_password:
        raise UnauthorizedError("用户名或密码错误")

    import json as _json

    role_codes = _json.loads(user.role_codes)
    token, expires_at = issue_token(user.user_id, role_codes)
    return {
        "accessToken": token,
        "tokenType": "Bearer",
        "expiresInSeconds": settings.jwt_expires_seconds,
        "user": get_access_context(db, user.user_id),
    }


def current_user_context(db: Session, authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("缺少 Bearer 访问令牌")
    user_id = verify_token(authorization[len("Bearer "):])
    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None or not user.enabled:
        raise UnauthorizedError("用户不存在或已禁用")
    return get_access_context(db, user_id)
