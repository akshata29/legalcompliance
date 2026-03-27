"""
RDF graph store — rdflib ConjunctiveGraph backed by Turtle file persistence.
Runs owlrl RDFS+OWL-RL reasoning after enrichment to infer implicit triples.
Thread-safe reads; writes use an asyncio lock.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Optional

import rdflib
from rdflib import ConjunctiveGraph, Graph, URIRef
from rdflib.namespace import RDF, RDFS, OWL

from ontology.fibo_schema import assert_schema
from ontology.namespaces import PREFIX_MAP

logger = logging.getLogger(__name__)

# Path to the persistent Turtle files
_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "ontology"
_SCHEMA_FILES = ["fibo_baseline.ttl", "eu_sec.ttl", "erisa.ttl", "om.ttl", "new_issuance.ttl"]
_RUNTIME_GRAPH = _DATA_DIR / "graph.ttl"


class GraphStore:
    """
    Singleton RDF graph store.
    - Loads schema + baseline TTL files on first access
    - Exposes the graph for SPARQL via `query()`
    - Merges new triples via `add_triples()` and optionally re-reasons
    - Persists the runtime subgraph to data/ontology/graph.ttl
    """

    _instance: Optional["GraphStore"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._graph = ConjunctiveGraph()
        self._write_lock = asyncio.Lock()
        self._bind_prefixes()
        self._load_schema()
        self._load_turtle_files()
        logger.info(
            "GraphStore initialised — %d triples loaded", len(self._graph)
        )

    @classmethod
    def get(cls) -> "GraphStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Test helper — force a fresh singleton."""
        with cls._lock:
            cls._instance = None

    # ── Binding helpers ───────────────────────────────────────────────────────

    def _bind_prefixes(self) -> None:
        for prefix, uri in PREFIX_MAP.items():
            self._graph.bind(prefix, uri)

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load_schema(self) -> None:
        """Assert OWL class/property declarations (no file needed)."""
        assert_schema(self._graph)

    def _load_turtle_files(self) -> None:
        """Parse all TTL ontology files if present; load runtime graph."""
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        for fname in _SCHEMA_FILES:
            path = _DATA_DIR / fname
            if path.exists():
                try:
                    self._graph.parse(str(path), format="turtle")
                    logger.info("Loaded ontology file: %s", fname)
                except Exception as exc:
                    logger.warning("Could not parse %s: %s", fname, exc)
        if _RUNTIME_GRAPH.exists():
            try:
                self._graph.parse(str(_RUNTIME_GRAPH), format="turtle")
                logger.info(
                    "Runtime graph loaded: %d triples", len(self._graph)
                )
            except Exception as exc:
                logger.warning("Could not parse runtime graph: %s", exc)

    # ── Write ─────────────────────────────────────────────────────────────────

    async def add_triples(
        self,
        triples: list[tuple],
        run_reasoner: bool = False,
        persist: bool = True,
    ) -> int:
        """Add triples to the graph, optionally reason, then persist."""
        async with self._write_lock:
            added = 0
            for triple in triples:
                if triple not in self._graph:
                    self._graph.add(triple)
                    added += 1
            if run_reasoner and added > 0:
                self._run_owlrl()
            if persist and added > 0:
                self._persist()
            return added

    def add_triples_sync(
        self,
        triples: list[tuple],
        run_reasoner: bool = False,
        persist: bool = True,
    ) -> int:
        """Synchronous variant for use in non-async contexts (e.g. startup)."""
        added = 0
        for triple in triples:
            if triple not in self._graph:
                self._graph.add(triple)
                added += 1
        if run_reasoner and added > 0:
            self._run_owlrl()
        if persist and added > 0:
            self._persist()
        return added

    # ── Reasoning ────────────────────────────────────────────────────────────

    def _run_owlrl(self) -> None:
        """Run RDFS + OWL-RL forward chaining to infer implicit triples."""
        try:
            import owlrl
            owlrl.DeductiveClosure(
                owlrl.OWLRL_Semantics,
                axiomatic_triples=False,
                datatype_axioms=False,
            ).expand(self._graph)
            logger.info(
                "OWL-RL reasoning complete — graph now has %d triples",
                len(self._graph),
            )
        except Exception as exc:
            logger.warning("OWL-RL reasoning failed (non-fatal): %s", exc)

    # ── Query ─────────────────────────────────────────────────────────────────

    def query(self, sparql: str, initNs: dict | None = None) -> rdflib.query.Result:
        """Execute a SPARQL SELECT/ASK/CONSTRUCT against the full graph."""
        ns = {**PREFIX_MAP}
        if initNs:
            ns.update(initNs)
        return self._graph.query(sparql, initNs=ns)

    def count(self) -> int:
        return len(self._graph)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _persist(self) -> None:
        """Serialize the runtime graph (excluding schema + provision triples) to TTL.

        Provisions are excluded because:
        - They are only used for SPARQL text queries (always in-memory)
        - They bloat the TTL with thousands of verbatim text literals
        - They are re-loaded from the document if the graph is re-enriched
        """
        try:
            runtime = Graph()
            for prefix, uri in PREFIX_MAP.items():
                runtime.bind(prefix, uri)
            for s, p, o in self._graph:
                if not isinstance(s, URIRef):
                    continue
                s_str = str(s)
                if not s_str.startswith("urn:"):
                    continue
                # Skip provision nodes — they are large and not visualized
                if s_str.startswith("urn:provision:"):
                    continue
                runtime.add((s, p, o))
            runtime.serialize(str(_RUNTIME_GRAPH), format="turtle")
        except Exception as exc:
            logger.warning("Graph persistence failed: %s", exc)

    def serialize_all(self, fmt: str = "turtle") -> str:
        """Return full graph as string (for debugging or export)."""
        return self._graph.serialize(format=fmt)

    # ── Export helpers ────────────────────────────────────────────────────────

    def get_all_subjects_of_type(self, rdf_type: URIRef) -> list[URIRef]:
        """Return all instance URIs of a given RDF type."""
        return [
            s for s, _, __ in self._graph.triples((None, RDF.type, rdf_type))
            if isinstance(s, URIRef)
        ]

    def get_triples_for_subject(self, subject: URIRef) -> list[tuple]:
        """Return all (p, o) pairs for a subject."""
        return [(p, o) for _, p, o in self._graph.triples((subject, None, None))]

    def remove_document_triples(self, doc_id: str) -> int:
        """
        Remove all triples belonging to a document and its derived nodes:
          - urn:document:{doc_id}       (document node)
          - urn:instrument:{doc_id}     (instrument node)
          - urn:finding:*               where lc:extractedFrom = document URI
          - urn:provision:*             where lc:containedInDocument = document URI

        Returns the number of triples removed. Persists automatically.
        """
        from ontology.namespaces import LC

        doc_uri = URIRef(f"urn:document:{doc_id}")
        inst_uri = URIRef(f"urn:instrument:{doc_id}")

        # Collect subjects that reference this document
        linked_subjects: set[URIRef] = set()
        for s, _, o in self._graph.triples((None, LC.extractedFrom, doc_uri)):
            if isinstance(s, URIRef):
                linked_subjects.add(s)
        for s, _, o in self._graph.triples((None, LC.containedInDocument, doc_uri)):
            if isinstance(s, URIRef):
                linked_subjects.add(s)
        # Also remove the document and instrument nodes themselves
        linked_subjects.add(doc_uri)
        linked_subjects.add(inst_uri)

        removed = 0
        for subj in linked_subjects:
            triples_to_remove = list(self._graph.triples((subj, None, None)))
            for triple in triples_to_remove:
                self._graph.remove(triple)
                removed += 1
            # Remove any triples pointing *to* this subject (e.g. doc -> hasInstrument -> inst)
            back_refs = list(self._graph.triples((None, None, subj)))
            for triple in back_refs:
                self._graph.remove(triple)
                removed += 1

        if removed:
            self._persist()
            logger.info("Removed %d triples for document %s", removed, doc_id)
        return removed
