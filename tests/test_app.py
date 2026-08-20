from __future__ import annotations

from fastapi.testclient import TestClient

from exitroute.app import create_app
from exitroute.config import Settings


def test_framework_errors_are_problem_documents_and_request_ids_are_safe() -> None:
    app = create_app(Settings(environment="test"))

    @app.get("/test-only-boom", include_in_schema=False)
    def boom() -> None:
        raise RuntimeError("private detail must not escape")

    with TestClient(app, raise_server_exceptions=False) as client:
        missing = client.get("/does-not-exist", headers={"X-Request-ID": "known-request"})
        assert missing.status_code == 404
        assert missing.json()["code"] == "not_found"
        assert missing.headers["x-request-id"] == "known-request"

        unexpected = client.get(
            "/test-only-boom", headers={"X-Request-ID": "invalid request id with spaces"}
        )
        assert unexpected.status_code == 500
        assert unexpected.json()["code"] == "internal_error"
        assert "private detail" not in unexpected.text
        assert unexpected.headers["x-request-id"] != "invalid request id with spaces"
