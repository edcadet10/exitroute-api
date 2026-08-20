#!/usr/bin/env python3
"""Validate the planning contract and its graph fixture without app code."""

from __future__ import annotations

import copy
import heapq
import json
import re
from pathlib import Path
from typing import Any

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "openapi.yaml"
EXAMPLE_PATH = ROOT / "examples" / "exit-route.json"
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def load_documents() -> tuple[dict[str, Any], dict[str, Any]]:
    with SPEC_PATH.open(encoding="utf-8") as handle:
        spec = yaml.safe_load(handle)
    with EXAMPLE_PATH.open(encoding="utf-8") as handle:
        example = json.load(handle)
    return spec, example


def resolve_pointer(document: Any, pointer: str) -> Any:
    if not pointer.startswith("#/"):
        raise AssertionError(f"external or invalid reference: {pointer}")
    value = document
    for raw_part in pointer[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or part not in value:
            raise AssertionError(f"unresolved reference: {pointer}")
        value = value[part]
    return value


def iter_refs(value: Any):
    if isinstance(value, dict):
        if "$ref" in value:
            yield value["$ref"]
        for child in value.values():
            yield from iter_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_refs(child)


def validate_openapi_structure(spec: dict[str, Any]) -> dict[str, int]:
    assert spec.get("openapi") == "3.1.0", "contract must use OpenAPI 3.1.0"
    assert spec.get("paths"), "contract has no paths"
    assert spec.get("components", {}).get("schemas"), "contract has no schemas"

    refs = list(iter_refs(spec))
    for ref in refs:
        resolve_pointer(spec, ref)

    operation_ids: list[str] = []
    operation_count = 0
    for path, path_item in spec["paths"].items():
        assert path.startswith("/"), f"invalid path: {path}"
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            operation_count += 1
            operation_id = operation.get("operationId")
            assert operation_id, f"missing operationId: {method.upper()} {path}"
            operation_ids.append(operation_id)
            responses = operation.get("responses", {})
            assert responses, f"missing responses: {operation_id}"
            assert any(str(code).startswith("2") for code in responses), (
                f"missing success response: {operation_id}"
            )

    assert len(operation_ids) == len(set(operation_ids)), "duplicate operationId"
    return {"references": len(refs), "operations": operation_count}


def rewrite_schema_refs(value: Any) -> Any:
    if isinstance(value, dict):
        rewritten = {}
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str) and child.startswith(
                "#/components/schemas/"
            ):
                rewritten[key] = child.replace("#/components/schemas/", "#/$defs/")
            else:
                rewritten[key] = rewrite_schema_refs(child)
        return rewritten
    if isinstance(value, list):
        return [rewrite_schema_refs(child) for child in value]
    return value


def validate_example_schema(spec: dict[str, Any], example: dict[str, Any]) -> None:
    component_schemas = spec["components"]["schemas"]
    exit_route = copy.deepcopy(component_schemas["ExitRoute"])
    schema = rewrite_schema_refs(exit_route)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$defs"] = {
        name: rewrite_schema_refs(copy.deepcopy(component))
        for name, component in component_schemas.items()
    }
    jsonschema.Draft202012Validator.check_schema(schema)
    errors = sorted(
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
        .iter_errors(example),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        rendered = "\n".join(
            f"- {'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
            for error in errors
        )
        raise AssertionError(f"example does not match ExitRoute schema:\n{rendered}")


def validate_graph(route: dict[str, Any]) -> dict[str, Any]:
    graph = route["graph"]
    nodes = graph["nodes"]
    node_ids = [node["id"] for node in nodes]
    assert len(node_ids) == len(set(node_ids)), "duplicate node ID"
    node_map = {node["id"]: node for node in nodes}
    assert graph["entry_node_id"] in node_map, "entry node is missing"

    choices: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if node["kind"] == "terminal":
            assert not node["choices"], f"terminal {node['id']} has choices"
        for choice in node["choices"]:
            assert choice["id"] not in choices, f"duplicate choice ID: {choice['id']}"
            assert choice["target_node_id"] in node_map, (
                f"dangling target: {choice['target_node_id']}"
            )
            choices[choice["id"]] = choice

    queue: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]] = [
        (0, graph["entry_node_id"], (), (graph["entry_node_id"],))
    ]
    best_cost: dict[str, int] = {}
    selected_choices: tuple[str, ...] | None = None
    selected_nodes: tuple[str, ...] | None = None
    path_cost = 0

    while queue:
        cost, node_id, choice_path, node_path = heapq.heappop(queue)
        if cost >= best_cost.get(node_id, 10**9):
            continue
        best_cost[node_id] = cost
        node = node_map[node_id]
        if node["state"] == "cancelled":
            path_cost = cost
            selected_choices = choice_path
            selected_nodes = node_path
            break
        for choice in node["choices"]:
            if choice["effect"] == "retain":
                continue
            heapq.heappush(
                queue,
                (
                    cost + choice["effort"],
                    choice["target_node_id"],
                    choice_path + (choice["id"],),
                    node_path + (choice["target_node_id"],),
                ),
            )

    assert selected_choices is not None, "no reachable cancelled terminal"
    assert list(selected_choices) == route["best_route"], (
        f"stored best route {route['best_route']} != computed {list(selected_choices)}"
    )

    friction = route["friction"]
    retention_offers = sum(
        choice["effect"] == "retain" for node in nodes for choice in node["choices"]
    )
    loops = sum(choice["effect"] == "loop" for node in nodes for choice in node["choices"])
    offline_handoff = any(
        node["kind"] == "handoff" for node in nodes
    ) or any(choice["effect"] == "handoff" for choice in choices.values())
    screens = sum(node_map[node_id]["kind"] != "terminal" for node_id in selected_nodes)
    effort_score = path_cost + retention_offers + 2 * loops + 5 * offline_handoff

    expected = {
        "screens": screens,
        "retention_offers": retention_offers,
        "loops": loops,
        "offline_handoff": offline_handoff,
        "effort_score": effort_score,
    }
    for field, value in expected.items():
        assert friction[field] == value, (
            f"friction {field}={friction[field]!r}; computed {value!r}"
        )
    return {"nodes": len(nodes), "choices": len(choices), "path_effort": path_cost}


def validate_local_doc_links() -> dict[str, int]:
    document_count = 0
    local_link_count = 0
    for document in ROOT.rglob("*.md"):
        document_count += 1
        contents = document.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(contents):
            target = raw_target.strip("<>")
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            local_link_count += 1
            path_text = target.split("#", 1)[0]
            assert path_text, f"empty local link in {document.relative_to(ROOT)}"
            resolved = (document.parent / path_text).resolve()
            assert ROOT in resolved.parents or resolved == ROOT, (
                f"local link escapes repository: {target}"
            )
            assert resolved.exists(), (
                f"broken local link in {document.relative_to(ROOT)}: {target}"
            )
    return {"documents": document_count, "local_links": local_link_count}


def main() -> None:
    spec, example = load_documents()
    contract = validate_openapi_structure(spec)
    validate_example_schema(spec, example)
    graph = validate_graph(example)
    docs = validate_local_doc_links()

    adversarial_rejections = 0

    extra_field = copy.deepcopy(example)
    extra_field["service"]["account_owner"] = "must never be accepted"
    try:
        validate_example_schema(spec, extra_field)
    except AssertionError:
        adversarial_rejections += 1
    else:
        raise AssertionError("schema accepted an undeclared service-specific field")

    dangling = copy.deepcopy(example)
    dangling["graph"]["nodes"][0]["choices"][0]["target_node_id"] = "missing"
    try:
        validate_graph(dangling)
    except AssertionError:
        adversarial_rejections += 1
    else:
        raise AssertionError("graph validator accepted a dangling edge")

    wrong_answer = copy.deepcopy(example)
    wrong_answer["best_route"] = ["manage", "continue", "keep-membership"]
    try:
        validate_graph(wrong_answer)
    except AssertionError:
        adversarial_rejections += 1
    else:
        raise AssertionError("graph validator accepted an incorrect best route")

    print(
        json.dumps(
            {
                "openapi": spec["openapi"],
                **contract,
                **graph,
                **docs,
                "example_schema_valid": True,
                "best_route_valid": True,
                "friction_valid": True,
                "adversarial_rejections": adversarial_rejections,
                "pass": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
