from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from exitroute.domain.graph import (
    GraphValidationError,
    RouteGraph,
    analyze_graph,
    content_fingerprint,
    representation_etag,
)
from exitroute.schemas import RevisionCreate
from tests.factories import graph_document


def test_graph_computes_deterministic_safe_route() -> None:
    graph = RouteGraph.model_validate(graph_document())
    result = analyze_graph(graph)

    assert result.best_route == ["manage", "continue-exit", "confirm-exit"]
    assert result.friction.screens == 3
    assert result.friction.retention_offers == 1
    assert result.friction.loops == 1
    assert result.friction.effort_score == 7


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data["nodes"][0].update(state="cancelled"), "terminal kind and state"),
        (
            lambda data: data["nodes"][1]["choices"][0].update(target_node_id="cancelled"),
            "retain must end in retained",
        ),
        (
            lambda data: data["nodes"][0]["choices"][0].update(target_node_id="retained"),
            "advance cannot retain",
        ),
        (
            lambda data: data["nodes"][2]["choices"][0].update(target_node_id="cancelled"),
            "loop edge does not form a cycle",
        ),
        (
            lambda data: data["nodes"][0]["choices"][0].update(target_node_id="missing"),
            "target does not exist",
        ),
        (
            lambda data: data["nodes"].append(
                {"id": "orphan", "kind": "terminal", "state": "unavailable", "choices": []}
            ),
            "unreachable nodes",
        ),
    ],
)
def test_graph_rejects_semantic_corruption(mutation: object, message: str) -> None:
    document = copy.deepcopy(graph_document())
    mutation(document)  # type: ignore[operator]
    graph = RouteGraph.model_validate(document)
    with pytest.raises(GraphValidationError, match=message):
        analyze_graph(graph)


def test_revision_input_cannot_override_server_derived_fields() -> None:
    with pytest.raises(ValidationError, match="fingerprint"):
        RevisionCreate.model_validate(
            {
                "route_id": "35d77b2b-1c99-4a2a-b5c5-8aff292685ed",
                "entry_url": "https://example.com/account",
                "graph": graph_document(),
                "change_summary": "test",
                "fingerprint": "a" * 64,
            }
        )


def test_fingerprint_and_etag_cover_content_and_mutable_status() -> None:
    graph = RouteGraph.model_validate(graph_document())
    computed = analyze_graph(graph)
    fingerprint = content_fingerprint("https://example.com/account", graph, computed)
    assert len(fingerprint) == 64
    assert fingerprint == content_fingerprint("https://example.com/account", graph, computed)
    assert fingerprint != content_fingerprint("https://example.com/settings", graph, computed)

    verified = representation_etag(fingerprint, "published", "verified", 2)
    stale = representation_etag(fingerprint, "published", "stale", 3)
    assert verified != stale
