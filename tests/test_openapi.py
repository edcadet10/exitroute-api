from __future__ import annotations

from typing import Any

from openapi_spec_validator import validate

from scripts.export_openapi import build_documents, render


def _contains_key(value: Any, target: str) -> bool:
    if isinstance(value, dict):
        return target in value or any(_contains_key(child, target) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, target) for child in value)
    return False


def test_generated_contracts_are_valid_and_security_is_explicit() -> None:
    primary, cloudflare = build_documents()
    validate(primary)
    validate(cloudflare)

    route_get = primary["paths"]["/v1/services/{service_slug}/exit-route"]["get"]
    assert any(item["name"] == "If-None-Match" for item in route_get["parameters"])
    assert "ETag" in route_get["responses"]["304"]["headers"]
    assert route_get["security"] == [{"ApiKeyAuth": []}]
    assert primary["paths"]["/v1/challenges/daily"]["get"].get("security") is None
    admin_security = primary["paths"]["/admin/v1/services"]["post"]["security"]
    assert admin_security == [{"BootstrapAdminAuth": []}, {"ApiKeyAuth": []}]

    assert cloudflare["openapi"] == "3.0.3"
    assert not _contains_key(cloudflare, "uniqueItems")
    assert render(primary).startswith("openapi: 3.1.0")
