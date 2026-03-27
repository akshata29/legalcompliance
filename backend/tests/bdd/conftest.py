"""
pytest-bdd conftest for Knowledge Graph BDD tests.
Wires feature files to step definitions and initialises test fixtures.
"""
from __future__ import annotations

import asyncio
import pytest
from pathlib import Path

# ── Feature file discovery ────────────────────────────────────────────────────

FEATURES_DIR = Path(__file__).parent.parent / "features"


# ── Event loop fixture for async helpers ─────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Provide a single event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Graph store isolation ─────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_graph():
    """
    Each BDD scenario gets a clean in-memory graph so tests are independent.
    We reset the singleton to force re-initialisation.
    """
    from backend.ontology import graph_store as gs_module
    # Store original singleton
    _orig = gs_module._instance  # type: ignore[attr-defined]
    gs_module._instance = None  # type: ignore[attr-defined]

    # Yield: test runs here
    yield

    # Restore original after test
    gs_module._instance = _orig  # type: ignore[attr-defined]


# ── Rule registry isolation ───────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_registry():
    """Force registry reload before each scenario."""
    from backend.rules import rule_registry as rr_module
    rr_module._registry_instance = None  # type: ignore[attr-defined]
    yield
