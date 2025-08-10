"""Tests for LightingManager calculation logic."""

import importlib.util
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "lighting_manager"
    / "manager.py"
)
spec = importlib.util.spec_from_file_location("manager", MODULE_PATH)
manager = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(manager)
LightingManager = manager.LightingManager


def test_priority_resolution():
    manager = LightingManager()
    layers = [
        {
            "layer_id": "base",
            "priority": 0,
            "force": False,
            "locked": False,
            "attributes": {"brightness": 100},
        },
        {
            "layer_id": "mode",
            "priority": 30,
            "force": False,
            "locked": False,
            "attributes": {"brightness": 200},
        },
    ]
    (
        ordered,
        winning,
        final_state,
        conflicts,
    ) = manager.calculate_zone_state(layers)
    assert winning == "mode"
    assert final_state["brightness"] == 200
    assert conflicts == []


def test_force_override():
    manager = LightingManager()
    layers = [
        {
            "layer_id": "base",
            "priority": 0,
            "force": True,
            "locked": False,
            "attributes": {"brightness": 100},
        },
        {
            "layer_id": "mode",
            "priority": 30,
            "force": False,
            "locked": False,
            "attributes": {"brightness": 200},
        },
    ]
    (
        _,
        winning,
        final_state,
        conflicts,
    ) = manager.calculate_zone_state(layers)
    assert winning == "base"
    assert final_state["brightness"] == 100
    assert conflicts == []


def test_priority_conflict():
    manager = LightingManager()
    layers = [
        {
            "layer_id": "a",
            "priority": 10,
            "force": False,
            "locked": False,
            "attributes": {},
        },
        {
            "layer_id": "b",
            "priority": 10,
            "force": False,
            "locked": False,
            "attributes": {},
        },
    ]
    (
        _,
        winning,
        _,
        conflicts,
    ) = manager.calculate_zone_state(layers)
    assert winning in {"a", "b"}
    assert conflicts and conflicts[0]["type"] == "priority_tie"


def test_force_conflict():
    manager = LightingManager()
    layers = [
        {
            "layer_id": "a",
            "priority": 10,
            "force": True,
            "locked": False,
            "attributes": {},
        },
        {
            "layer_id": "b",
            "priority": 20,
            "force": True,
            "locked": False,
            "attributes": {},
        },
    ]
    (
        _,
        winning,
        _,
        conflicts,
    ) = manager.calculate_zone_state(layers)
    assert winning == "b"
    assert conflicts and conflicts[0]["type"] == "force"
