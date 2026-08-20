"""Fictional, reusable test documents."""

from __future__ import annotations

from typing import Any


def graph_document() -> dict[str, Any]:
    return {
        "entry_node_id": "account",
        "nodes": [
            {
                "id": "account",
                "kind": "screen",
                "state": None,
                "choices": [
                    {
                        "id": "manage",
                        "label": "Manage membership",
                        "target_node_id": "offer",
                        "effect": "advance",
                        "effort": 1,
                        "prominence": "secondary",
                    }
                ],
            },
            {
                "id": "offer",
                "kind": "screen",
                "state": None,
                "choices": [
                    {
                        "id": "keep-plan",
                        "label": "Keep membership",
                        "target_node_id": "retained",
                        "effect": "retain",
                        "effort": 1,
                        "prominence": "primary",
                    },
                    {
                        "id": "continue-exit",
                        "label": "Continue cancellation",
                        "target_node_id": "confirm",
                        "effect": "advance",
                        "effort": 2,
                        "prominence": "subdued",
                    },
                ],
            },
            {
                "id": "confirm",
                "kind": "screen",
                "state": None,
                "choices": [
                    {
                        "id": "back-to-offer",
                        "label": "Go back",
                        "target_node_id": "offer",
                        "effect": "loop",
                        "effort": 1,
                        "prominence": "primary",
                    },
                    {
                        "id": "confirm-exit",
                        "label": "Confirm cancellation",
                        "target_node_id": "cancelled",
                        "effect": "advance",
                        "effort": 1,
                        "prominence": "ambiguous",
                    },
                ],
            },
            {"id": "retained", "kind": "terminal", "state": "retained", "choices": []},
            {"id": "cancelled", "kind": "terminal", "state": "cancelled", "choices": []},
        ],
    }
