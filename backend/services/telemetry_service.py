"""
Telemetry Service
-----------------
Lightweight in-process metrics for the Knowledge Graph feature.
Records: response latency, graph query latency, LLM token usage,
rule evaluation outcomes, SLA breaches.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class QueryRecord:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    question: str = ""
    intent: str = ""
    persona: Optional[str] = None
    latency_ms: float = 0.0
    graph_query_ms: float = 0.0
    llm_tokens_used: int = 0
    sla_breach: bool = False
    error: Optional[str] = None


# Global ring-buffer: keep last 1000 records (avoids unbounded growth)
_records: deque[QueryRecord] = deque(maxlen=1000)

# Counters
_intent_counts: dict[str, int] = defaultdict(int)
_sla_breach_count: int = 0
_total_queries: int = 0

# SLA threshold (default: 5 seconds)
SLA_THRESHOLD_MS: float = 5000.0


def record_query(
    question: str,
    intent: str,
    *,
    persona: Optional[str] = None,
    latency_ms: float,
    graph_query_ms: float = 0.0,
    llm_tokens_used: int = 0,
    error: Optional[str] = None,
) -> QueryRecord:
    global _total_queries, _sla_breach_count
    sla_breach = latency_ms > SLA_THRESHOLD_MS
    _total_queries += 1
    _intent_counts[intent] += 1
    if sla_breach:
        _sla_breach_count += 1

    rec = QueryRecord(
        question=question,
        intent=intent,
        persona=persona,
        latency_ms=latency_ms,
        graph_query_ms=graph_query_ms,
        llm_tokens_used=llm_tokens_used,
        sla_breach=sla_breach,
        error=error,
    )
    _records.append(rec)
    return rec


def get_summary() -> dict:
    records = list(_records)
    if not records:
        return {
            "total_queries": 0,
            "avg_latency_ms": 0,
            "p95_latency_ms": 0,
            "sla_breach_rate": 0,
            "intent_distribution": {},
        }

    latencies = sorted(r.latency_ms for r in records)
    n = len(latencies)
    avg = sum(latencies) / n
    p95 = latencies[int(n * 0.95) - 1]

    return {
        "total_queries": _total_queries,
        "avg_latency_ms": round(avg, 1),
        "p95_latency_ms": round(p95, 1),
        "sla_breach_count": _sla_breach_count,
        "sla_breach_rate": round(_sla_breach_count / max(_total_queries, 1), 4),
        "intent_distribution": dict(_intent_counts),
        "recent_errors": [r.error for r in records[-20:] if r.error],
    }


def get_recent(n: int = 50) -> list[dict]:
    return [
        {
            "timestamp": r.timestamp,
            "intent": r.intent,
            "persona": r.persona,
            "latency_ms": r.latency_ms,
            "sla_breach": r.sla_breach,
            "error": r.error,
        }
        for r in list(_records)[-n:]
    ]


class LatencyTimer:
    """Context manager for measuring elapsed time."""

    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "LatencyTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args) -> None:
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000
