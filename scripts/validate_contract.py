#!/usr/bin/env python3
"""Compatibility entry point for contract, example, graph, and doc-link checks."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from openapi_spec_validator import validate

from exitroute.domain.graph import analyze_graph, content_fingerprint
from exitroute.schemas import ExitRouteView

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def validate_local_doc_links() -> int:
    checked = 0
    documents = [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md")]
    for document in documents:
        contents = document.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(contents):
            target = raw_target.strip("<>")
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            path_text = target.split("#", 1)[0]
            resolved = (document.parent / path_text).resolve()
            if ROOT not in resolved.parents and resolved != ROOT:
                raise AssertionError(f"local link escapes repository: {target}")
            if not resolved.exists():
                raise AssertionError(f"broken local link in {document.relative_to(ROOT)}: {target}")
            checked += 1
    return checked


def main() -> None:
    for filename in ("openapi.yaml", "openapi.cloudflare.yaml"):
        document = yaml.safe_load((ROOT / filename).read_text(encoding="utf-8"))
        validate(document)

    raw_example = json.loads((ROOT / "examples/exit-route.json").read_text(encoding="utf-8"))
    example = ExitRouteView.model_validate(raw_example)
    computed = analyze_graph(example.graph)
    assert computed.best_route == example.best_route
    assert computed.friction == example.friction
    assert content_fingerprint(example.entry_url, example.graph, computed) == example.fingerprint
    links = validate_local_doc_links()
    print(
        json.dumps(
            {
                "openapi_contracts": 2,
                "example_valid": True,
                "graph_semantics_valid": True,
                "fingerprint_valid": True,
                "local_links": links,
                "pass": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
