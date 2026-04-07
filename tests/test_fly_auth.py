from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import time
import unittest
from urllib.parse import urlencode

from workbench_auth import password_generate_hash


REPO_ROOT = os.path.dirname(os.path.dirname(__file__))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class FlyAuthIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.port = _free_port()
        password_hash = password_generate_hash(b"correct horse battery staple")
        env = os.environ.copy()
        env.update(
            {
                "PORT": str(self.port),
                "WORKBENCH_AUTOSTART": "0",
                "WORKBENCH_AUTH_REQUIRED": "1",
                "WORKBENCH_AUTH_SESSION_SECRET": "test-session-secret-0123456789",
                "WORKBENCH_AUTH_USERS_JSON": json.dumps({"admin": {"PASSWORD": password_hash}}),
                "PYTHONUNBUFFERED": "1",
            }
        )
        self.proc = subprocess.Popen(
            ["uv", "run", "python", "fly_entrypoint.py"],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._wait_until_ready()

    def tearDown(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)

    def test_auth_flow(self) -> None:
        health = self._request("GET", "/healthz")
        self.assertEqual(200, health["status"])

        root = self._request("GET", "/")
        self.assertEqual(303, root["status"])
        self.assertTrue(root["headers"]["Location"].startswith("/login?next=/"))

        login_page = self._request("GET", "/login?next=/api/workbench/status")
        self.assertEqual(200, login_page["status"])
        self.assertIn("Sign in", login_page["body"])

        login = self._request(
            "POST",
            "/login",
            body=urlencode(
                {
                    "username": "admin",
                    "password": "correct horse battery staple",
                    "next": "/api/workbench/status",
                }
            ),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(303, login["status"])
        self.assertEqual("/api/workbench/status", login["headers"]["Location"])
        session_cookie = login["headers"].get("Set-Cookie")
        self.assertIsNotNone(session_cookie)

        api = self._request("GET", "/api/workbench/status", headers={"Cookie": session_cookie})
        self.assertEqual(200, api["status"])
        self.assertIn('"dashboard"', api["body"])

        logout = self._request("GET", "/logout", headers={"Cookie": session_cookie})
        self.assertEqual(303, logout["status"])
        self.assertEqual("/login", logout["headers"]["Location"])

        api_after_logout = self._request("GET", "/api/workbench/status")
        self.assertEqual(401, api_after_logout["status"])

    def _wait_until_ready(self) -> None:
        deadline = time.time() + 20
        last_error: Exception | None = None
        while time.time() < deadline:
            if self.proc.poll() is not None:
                stdout, stderr = self.proc.communicate(timeout=1)
                raise AssertionError(f"fly_entrypoint.py exited early\nstdout:\n{stdout}\nstderr:\n{stderr}")
            try:
                response = self._request("GET", "/healthz")
                if response["status"] == 200:
                    return
            except Exception as exc:  # pragma: no cover - retry loop
                last_error = exc
            time.sleep(0.2)
        raise AssertionError(f"server did not become ready: {last_error}")

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            payload = response.read().decode("utf-8", errors="ignore")
            return {
                "status": response.status,
                "headers": {key: value for key, value in response.getheaders()},
                "body": payload,
            }
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
