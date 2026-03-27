"""
Export rdflib graph to NetworkX dict format for frontend visualization.
Returns nodes+edges JSON that react-force-graph-2d can consume directly.
"""
from __future__ import annotations

from ontology.graph_query import get_full_graph_json


def export_for_visualization(persona: str | None = None) -> dict:
    """
    Return {nodes, edges} dict ready for react-force-graph-2d.
    Optionally filter by persona to reduce visual noise.
    """
    data = get_full_graph_json()
    nodes = data["nodes"]
    edges = data["edges"]

    # Persona-based filtering
    if persona == "trader":
        # Show instruments + issuers + readiness
        allowed_types = {"Instrument", "Issuer", "Finding"}
        nodes = [n for n in nodes if n.get("type") in allowed_types]
    elif persona == "compliance":
        # Show findings + provisions + rules
        allowed_types = {"Finding", "Provision", "Document", "Instrument"}
        nodes = [n for n in nodes if n.get("type") in allowed_types]
    elif persona == "legal":
        # Show rules + provisions + documents
        allowed_types = {"Rule", "Provision", "Document", "Instrument"}
        nodes = [n for n in nodes if n.get("type") in allowed_types]
    elif persona == "data_management":
        # Show all
        pass

    node_ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "persona_filter": persona or "all",
        },
    }
