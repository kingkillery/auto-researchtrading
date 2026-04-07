from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import secrets
import time
from dataclasses import dataclass
from http import cookies
from typing import Any
from urllib.parse import parse_qs, quote


DEFAULT_SESSION_TTL_SECONDS = 60 * 60 * 12
SESSION_COOKIE_NAME = "workbench_session"


def password_generate_hash(initial_password_bytes: bytes, *, salt: str | None = None) -> dict[str, Any]:
    if salt is None:
        salt = base64.b64encode(secrets.token_bytes(16)).decode()
    algs = [
        {
            "type": "scrypt",
            "salt": salt,
            "n": 2**14,
            "r": 8,
            "p": 5,
            "maxmem": 0,
            "dklen": 64,
        }
    ]
    current = initial_password_bytes
    for algorithm in algs:
        if algorithm["type"] != "scrypt":
            raise NotImplementedError(f"unsupported password algorithm: {algorithm['type']}")
        current = hashlib.scrypt(
            current,
            salt=base64.b64decode(algorithm["salt"]),
            n=algorithm["n"],
            r=algorithm["r"],
            p=algorithm["p"],
            maxmem=algorithm["maxmem"],
            dklen=algorithm["dklen"],
        )
    return {"algs": algs, "final_hash": base64.b64encode(current).decode()}


def password_check(password_ref: dict[str, Any], submitted_password: str) -> bool:
    current = submitted_password.encode("utf-8")
    for algorithm in password_ref["algs"]:
        if algorithm["type"] != "scrypt":
            raise NotImplementedError(f"unsupported password algorithm: {algorithm['type']}")
        current = hashlib.scrypt(
            current,
            salt=base64.b64decode(algorithm["salt"]),
            n=algorithm["n"],
            r=algorithm["r"],
            p=algorithm["p"],
            maxmem=algorithm["maxmem"],
            dklen=algorithm["dklen"],
        )
    return secrets.compare_digest(current, base64.b64decode(password_ref["final_hash"]))


@dataclass(frozen=True)
class AuthConfig:
    required: bool
    session_secret: str | None
    users: dict[str, dict[str, Any]]
    session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS
    realm: str = "Auto Research Trading"

    def validate(self) -> None:
        if not self.required:
            return
        if not self.session_secret:
            raise ValueError("WORKBENCH_AUTH_SESSION_SECRET is required when auth is enabled")
        if not self.users:
            raise ValueError("WORKBENCH_AUTH_USERS_JSON is required when auth is enabled")


def load_auth_config_from_env(env: dict[str, str]) -> AuthConfig:
    required = env.get("WORKBENCH_AUTH_REQUIRED", "").lower() in {"1", "true", "yes", "on"}
    session_secret = env.get("WORKBENCH_AUTH_SESSION_SECRET")
    users_json = env.get("WORKBENCH_AUTH_USERS_JSON", "")
    users: dict[str, dict[str, Any]] = {}
    if users_json:
        parsed = json.loads(users_json)
        if not isinstance(parsed, dict):
            raise ValueError("WORKBENCH_AUTH_USERS_JSON must decode to an object keyed by username")
        users = parsed
    ttl_raw = env.get("WORKBENCH_AUTH_SESSION_TTL_SECONDS", str(DEFAULT_SESSION_TTL_SECONDS))
    realm = env.get("WORKBENCH_AUTH_REALM", "Auto Research Trading")
    config = AuthConfig(
        required=required,
        session_secret=session_secret,
        users=users,
        session_ttl_seconds=int(ttl_raw),
        realm=realm,
    )
    config.validate()
    return config


class SessionSigner:
    def __init__(self, secret: str, *, ttl_seconds: int) -> None:
        self.secret = secret.encode("utf-8")
        self.ttl_seconds = ttl_seconds

    def sign(self, payload: dict[str, Any]) -> str:
        encoded = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode("utf-8")).decode("ascii").rstrip("=")
        issued_at = int(time.time())
        digest = hmac.new(self.secret, digestmod=hashlib.sha256)
        digest.update(encoded.encode("ascii"))
        digest.update(str(issued_at).encode("ascii"))
        return f"{encoded}.{issued_at}.{digest.hexdigest()}"

    def verify(self, signed_value: str) -> dict[str, Any] | None:
        try:
            encoded, issued_at_raw, provided_digest = signed_value.split(".", 2)
            issued_at = int(issued_at_raw)
        except (AttributeError, ValueError):
            return None
        digest = hmac.new(self.secret, digestmod=hashlib.sha256)
        digest.update(encoded.encode("ascii"))
        digest.update(str(issued_at).encode("ascii"))
        expected_digest = digest.hexdigest()
        if not secrets.compare_digest(expected_digest, provided_digest):
            return None
        if issued_at + self.ttl_seconds < int(time.time()):
            return None
        padded = encoded + ("=" * (-len(encoded) % 4))
        try:
            payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return payload


class WorkbenchAuth:
    def __init__(self, config: AuthConfig) -> None:
        self.config = config
        self.signer = SessionSigner(config.session_secret or "", ttl_seconds=config.session_ttl_seconds) if config.required else None

    @property
    def enabled(self) -> bool:
        return self.config.required

    def authenticate_credentials(self, username: str, password: str) -> bool:
        user_ref = self.config.users.get(username)
        if user_ref is None:
            return False
        password_ref = user_ref.get("PASSWORD")
        if not isinstance(password_ref, dict):
            return False
        try:
            return password_check(password_ref, password)
        except (KeyError, TypeError, ValueError):
            return False

    def current_user(self, cookie_header: str | None) -> dict[str, Any] | None:
        if not self.enabled:
            return {"username": "anonymous"}
        if not cookie_header or self.signer is None:
            return None
        jar = cookies.SimpleCookie()
        jar.load(cookie_header)
        morsel = jar.get(SESSION_COOKIE_NAME)
        if morsel is None:
            return None
        payload = self.signer.verify(morsel.value)
        if payload is None:
            return None
        username = payload.get("username")
        if not isinstance(username, str) or username not in self.config.users:
            return None
        return {"username": username}

    def build_session_cookie(self, username: str, *, secure: bool) -> str:
        if self.signer is None:
            raise RuntimeError("auth is not enabled")
        jar = cookies.SimpleCookie()
        jar[SESSION_COOKIE_NAME] = self.signer.sign({"username": username})
        jar[SESSION_COOKIE_NAME]["path"] = "/"
        jar[SESSION_COOKIE_NAME]["httponly"] = True
        jar[SESSION_COOKIE_NAME]["max-age"] = str(self.config.session_ttl_seconds)
        jar[SESSION_COOKIE_NAME]["samesite"] = "Strict"
        if secure:
            jar[SESSION_COOKIE_NAME]["secure"] = True
        return jar.output(header="").strip()

    def clear_session_cookie(self, *, secure: bool) -> str:
        jar = cookies.SimpleCookie()
        jar[SESSION_COOKIE_NAME] = ""
        jar[SESSION_COOKIE_NAME]["path"] = "/"
        jar[SESSION_COOKIE_NAME]["httponly"] = True
        jar[SESSION_COOKIE_NAME]["max-age"] = "0"
        jar[SESSION_COOKIE_NAME]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
        jar[SESSION_COOKIE_NAME]["samesite"] = "Strict"
        if secure:
            jar[SESSION_COOKIE_NAME]["secure"] = True
        return jar.output(header="").strip()

    def login_html(self, *, next_path: str | None = None, error_message: str | None = None) -> str:
        escaped_next = html.escape(next_path or "/")
        error_block = ""
        if error_message:
            error_block = f"<p style='color:#f17c7c;font-weight:700'>{html.escape(error_message)}</p>"
        return (
            "<!doctype html><html><head><meta charset='utf-8'><title>Workbench Login</title>"
            "<style>"
            "body{font-family:Segoe UI,Arial,sans-serif;background:#081322;color:#e8eef7;display:flex;min-height:100vh;"
            "align-items:center;justify-content:center;margin:0}"
            ".card{width:min(420px,92vw);background:#0c1b2ef2;border:1px solid #94a3b81f;border-radius:18px;padding:24px}"
            "label{display:block;margin-bottom:12px;font-weight:600}"
            "input{width:100%;padding:10px 12px;margin-top:6px;border-radius:10px;border:1px solid #39506b;background:#081322;color:#e8eef7}"
            "button{width:100%;margin-top:12px;padding:11px 14px;border:0;border-radius:999px;background:#45d0a1;color:#041018;font-weight:700;cursor:pointer}"
            "p{line-height:1.5;color:#8fa3bd}"
            "</style></head><body><main class='card'>"
            f"<h1>{html.escape(self.config.realm)}</h1>"
            "<p>Sign in with a configured workbench account.</p>"
            f"{error_block}"
            "<form method='post' action='/login'>"
            f"<input type='hidden' name='next' value='{escaped_next}'>"
            "<label>Username<input name='username' autocomplete='username' required></label>"
            "<label>Password<input type='password' name='password' autocomplete='current-password' required></label>"
            "<button type='submit'>Sign in</button>"
            "</form></main></body></html>"
        )

    @staticmethod
    def parse_form_body(body: bytes) -> dict[str, str]:
        parsed = parse_qs(body.decode("utf-8"), keep_blank_values=False)
        return {key: values[-1] for key, values in parsed.items() if values}

    @staticmethod
    def sanitize_next_path(next_path: str | None) -> str:
        if not next_path or not next_path.startswith("/"):
            return "/"
        if next_path.startswith("//"):
            return "/"
        return next_path

    @staticmethod
    def redirect_location(next_path: str | None) -> str:
        return quote(WorkbenchAuth.sanitize_next_path(next_path), safe="/?=&")
