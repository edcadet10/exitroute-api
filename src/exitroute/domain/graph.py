"""Route-graph validation, path selection, scoring, and fingerprinting."""

from __future__ import annotations

import hashlib
import heapq
import json
from collections import deque
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

Slug = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=2, max_length=80)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Platform(StrEnum):
    WEB = "web"
    IOS = "ios"
    ANDROID = "android"
    PHONE = "phone"
    MAIL = "mail"
    IN_PERSON = "in_person"


class Outcome(StrEnum):
    CANCEL_SUBSCRIPTION = "cancel_subscription"


class NodeKind(StrEnum):
    SCREEN = "screen"
    OS_SETTINGS = "os_settings"
    HANDOFF = "handoff"
    TERMINAL = "terminal"


class TerminalState(StrEnum):
    CANCELLED = "cancelled"
    RETAINED = "retained"
    UNAVAILABLE = "unavailable"


class ChoiceEffect(StrEnum):
    ADVANCE = "advance"
    LOOP = "loop"
    RETAIN = "retain"
    HANDOFF = "handoff"


class Prominence(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    SUBDUED = "subdued"
    AMBIGUOUS = "ambiguous"


class PublicationState(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


class TrustState(StrEnum):
    PROVISIONAL = "provisional"
    VERIFIED = "verified"
    STALE = "stale"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Choice(StrictModel):
    id: Slug
    label: Annotated[str, Field(min_length=1, max_length=160)]
    target_node_id: Slug
    effect: ChoiceEffect
    effort: Annotated[int, Field(ge=0, le=100)]
    prominence: Prominence


class RouteNode(StrictModel):
    id: Slug
    kind: NodeKind
    state: TerminalState | None = None
    choices: Annotated[list[Choice], Field(max_length=30)]


class RouteGraph(StrictModel):
    entry_node_id: Slug
    nodes: Annotated[list[RouteNode], Field(min_length=2, max_length=100)]


class Friction(StrictModel):
    screens: Annotated[int, Field(ge=0)]
    retention_offers: Annotated[int, Field(ge=0)]
    loops: Annotated[int, Field(ge=0)]
    offline_handoff: bool
    effort_score: Annotated[int, Field(ge=0)]
    algorithm_version: Literal["friction-v1"] = "friction-v1"


class ComputedRoute(StrictModel):
    best_route: list[str]
    visited_nodes: list[str]
    friction: Friction


class GraphValidationError(ValueError):
    """Raised when a graph is structurally valid JSON but semantically unsafe."""


def _index_graph(graph: RouteGraph) -> tuple[dict[str, RouteNode], dict[str, Choice]]:
    nodes: dict[str, RouteNode] = {}
    choices: dict[str, Choice] = {}
    for node in graph.nodes:
        if node.id in nodes:
            raise GraphValidationError(f"duplicate node id: {node.id}")
        nodes[node.id] = node
        for choice in node.choices:
            if choice.id in choices:
                raise GraphValidationError(f"duplicate choice id: {choice.id}")
            choices[choice.id] = choice
    if graph.entry_node_id not in nodes:
        raise GraphValidationError("entry node does not exist")
    return nodes, choices


def _validate_node_shapes(nodes: dict[str, RouteNode]) -> None:
    for node in nodes.values():
        is_terminal = node.kind is NodeKind.TERMINAL
        if is_terminal != (node.state is not None):
            raise GraphValidationError(f"node {node.id}: terminal kind and state must agree")
        if is_terminal and node.choices:
            raise GraphValidationError(f"terminal node {node.id} cannot have choices")
        if not is_terminal and not node.choices:
            raise GraphValidationError(f"nonterminal node {node.id} needs at least one choice")


def _can_reach(start: str, target: str, nodes: dict[str, RouteNode]) -> bool:
    pending = [start]
    seen: set[str] = set()
    while pending:
        node_id = pending.pop()
        if node_id == target:
            return True
        if node_id in seen:
            continue
        seen.add(node_id)
        pending.extend(choice.target_node_id for choice in nodes[node_id].choices)
    return False


def _validate_edges(nodes: dict[str, RouteNode]) -> None:
    for source in nodes.values():
        for choice in source.choices:
            if choice.target_node_id not in nodes:
                raise GraphValidationError(f"choice {choice.id}: target does not exist")
    for source in nodes.values():
        for choice in source.choices:
            target = nodes[choice.target_node_id]
            if choice.effect is ChoiceEffect.RETAIN and target.state is not TerminalState.RETAINED:
                raise GraphValidationError(f"choice {choice.id}: retain must end in retained")
            if choice.effect is ChoiceEffect.HANDOFF and target.kind is not NodeKind.HANDOFF:
                raise GraphValidationError(
                    f"choice {choice.id}: handoff must target a handoff node"
                )
            if choice.effect is ChoiceEffect.ADVANCE and target.state is TerminalState.RETAINED:
                raise GraphValidationError(f"choice {choice.id}: advance cannot retain the user")
            if choice.effect is ChoiceEffect.LOOP and not _can_reach(target.id, source.id, nodes):
                raise GraphValidationError(f"choice {choice.id}: loop edge does not form a cycle")


def _validate_reachability(entry: str, nodes: dict[str, RouteNode]) -> None:
    pending = deque([entry])
    reached: set[str] = set()
    while pending:
        node_id = pending.popleft()
        if node_id in reached:
            continue
        reached.add(node_id)
        pending.extend(choice.target_node_id for choice in nodes[node_id].choices)
    unreachable = sorted(set(nodes) - reached)
    if unreachable:
        raise GraphValidationError(f"unreachable nodes: {', '.join(unreachable)}")


def _lowest_effort_path(
    entry: str, nodes: dict[str, RouteNode]
) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    queue: list[tuple[int, tuple[str, ...], str, tuple[str, ...]]] = [(0, (), entry, (entry,))]
    best: dict[str, tuple[int, tuple[str, ...]]] = {}
    while queue:
        cost, choice_path, node_id, node_path = heapq.heappop(queue)
        rank = (cost, choice_path)
        if node_id in best and best[node_id] <= rank:
            continue
        best[node_id] = rank
        node = nodes[node_id]
        if node.state is TerminalState.CANCELLED:
            return cost, choice_path, node_path
        for choice in node.choices:
            if choice.effect in {ChoiceEffect.RETAIN, ChoiceEffect.LOOP}:
                continue
            heapq.heappush(
                queue,
                (
                    cost + choice.effort,
                    (*choice_path, choice.id),
                    choice.target_node_id,
                    (*node_path, choice.target_node_id),
                ),
            )
    raise GraphValidationError("no safe path reaches a cancelled terminal")


def analyze_graph(graph: RouteGraph) -> ComputedRoute:
    """Validate the full graph and calculate its deterministic recommended route."""

    nodes, choices = _index_graph(graph)
    _validate_node_shapes(nodes)
    _validate_edges(nodes)
    _validate_reachability(graph.entry_node_id, nodes)
    path_effort, choice_path, node_path = _lowest_effort_path(graph.entry_node_id, nodes)
    retention_offers = sum(choice.effect is ChoiceEffect.RETAIN for choice in choices.values())
    loops = sum(choice.effect is ChoiceEffect.LOOP for choice in choices.values())
    path_choices = set(choice_path)
    offline_handoff = any(
        node.kind is NodeKind.HANDOFF for node in (nodes[node_id] for node_id in node_path)
    ) or any(
        choice.effect is ChoiceEffect.HANDOFF
        for choice_id, choice in choices.items()
        if choice_id in path_choices
    )
    screens = sum(nodes[node_id].kind is not NodeKind.TERMINAL for node_id in node_path)
    friction = Friction(
        screens=screens,
        retention_offers=retention_offers,
        loops=loops,
        offline_handoff=offline_handoff,
        effort_score=path_effort + retention_offers + (2 * loops) + (5 * offline_handoff),
    )
    return ComputedRoute(
        best_route=list(choice_path), visited_nodes=list(node_path), friction=friction
    )


def content_fingerprint(entry_url: HttpUrl | str, graph: RouteGraph, route: ComputedRoute) -> str:
    """Hash canonical, server-derived revision contents."""

    document = {
        "algorithm_version": route.friction.algorithm_version,
        "best_route": route.best_route,
        "entry_url": str(entry_url),
        "friction": route.friction.model_dump(mode="json"),
        "graph": graph.model_dump(mode="json"),
    }
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def representation_etag(fingerprint: str, publication: str, trust: str, version: int) -> str:
    """Create a strong ETag that changes when freshness/publication metadata changes."""

    state = f"{fingerprint}:{publication}:{trust}:{version}".encode()
    return f'"{hashlib.sha256(state).hexdigest()}"'
