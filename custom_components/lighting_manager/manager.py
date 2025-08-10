"""Calculation helpers for Lighting Manager."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple


_LOGGER = logging.getLogger(__name__)


class LightingManager:
    """Pure calculation logic for resolving layer states."""

    def calculate_zone_state(
        self, layers: List[Dict[str, Any]]
    ) -> Tuple[
        List[Dict[str, Any]],
        str | None,
        Dict[str, Any],
        List[Dict[str, Any]],
    ]:
        """Return ordered layers with winner, final state and conflicts."""
        if not layers:
            return [], None, {}, []

        conflicts: List[Dict[str, Any]] = []
        forced = [layer for layer in layers if layer.get("force")]
        if len(forced) > 1:
            conflicts.append(
                {
                    "type": "force",
                    "layers": [layer["layer_id"] for layer in forced],
                }
            )
            forced.sort(key=lambda x: x["priority"], reverse=True)
            ordered = sorted(
                layers, key=lambda x: (-int(x.get("force")), x["priority"])
            )
            winner = forced[0]
        elif forced:
            ordered = sorted(
                layers, key=lambda x: (-int(x.get("force")), x["priority"])
            )
            winner = forced[0]
        else:
            ordered = sorted(layers, key=lambda x: x["priority"], reverse=True)
            max_prio = ordered[0]["priority"]
            top_layers = [
                layer for layer in ordered if layer["priority"] == max_prio
            ]
            if len(top_layers) > 1:
                conflicts.append(
                    {
                        "type": "priority_tie",
                        "layers": [layer["layer_id"] for layer in top_layers],
                    }
                )
            winner = ordered[0]

        if conflicts:
            _LOGGER.warning("Layer conflict detected: %s", conflicts)

        attrs = winner.get("attributes", {})
        final_state: Dict[str, Any] = {}
        for key in (
            "brightness",
            "color_temp",
            "rgb_color",
            "transition",
            "effect",
        ):
            if (value := attrs.get(key)) is not None:
                final_state[key] = value

        return ordered, winner.get("layer_id"), final_state, conflicts
