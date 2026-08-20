#!/usr/bin/env python3
"""Export deterministic primary and Cloudflare-compatible OpenAPI artifacts."""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any

import yaml

from exitroute.app import create_app
from exitroute.config import Settings

ROOT = Path(__file__).resolve().parents[1]
PRIMARY_PATH = ROOT / "openapi.yaml"
CLOUDFLARE_PATH = ROOT / "openapi.cloudflare.yaml"


class LiteralString(str):
    pass


def _literal_presenter(dumper: yaml.SafeDumper, data: LiteralString) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.SafeDumper.add_representer(LiteralString, _literal_presenter)


def _multiline_strings(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _multiline_strings(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_multiline_strings(child) for child in value]
    if isinstance(value, str) and "\n" in value:
        return LiteralString(value)
    return value


def _oas30_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [_oas30_schema(child) for child in value]
    if not isinstance(value, dict):
        return value
    rewritten = {key: _oas30_schema(child) for key, child in value.items()}
    rewritten.pop("uniqueItems", None)  # Cloudflare API Shield does not enforce this keyword.
    if "const" in rewritten:
        rewritten["enum"] = [rewritten.pop("const")]
    alternatives = rewritten.get("anyOf")
    if isinstance(alternatives, list):
        non_null = [item for item in alternatives if item != {"type": "null"}]
        if len(non_null) == 1 and len(alternatives) == 2 and isinstance(non_null[0], dict):
            nullable = {**non_null[0], "nullable": True}
            rewritten.pop("anyOf")
            rewritten.update(nullable)
    return rewritten


def build_documents() -> tuple[dict[str, Any], dict[str, Any]]:
    app = create_app(Settings(environment="test"))
    primary = app.openapi()
    cloudflare = _oas30_schema(copy.deepcopy(primary))
    cloudflare["openapi"] = "3.0.3"
    cloudflare["info"].pop("summary", None)
    cloudflare["info"].get("license", {}).pop("identifier", None)
    return primary, cloudflare


def render(document: dict[str, Any]) -> str:
    return yaml.safe_dump(
        _multiline_strings(document),
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if committed artifacts drift.")
    arguments = parser.parse_args()
    primary, cloudflare = build_documents()
    expected = {
        PRIMARY_PATH: render(primary),
        CLOUDFLARE_PATH: render(cloudflare),
    }
    drift = [
        path
        for path, contents in expected.items()
        if not path.exists() or path.read_text() != contents
    ]
    if arguments.check:
        if drift:
            parser.error("OpenAPI artifacts are stale: " + ", ".join(path.name for path in drift))
        return 0
    for path, contents in expected.items():
        path.write_text(contents, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
