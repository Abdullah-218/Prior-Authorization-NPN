"""
Priority score history — a plain time-series log, NOT a LangGraph
checkpoint. Reuses the SAME MongoDB cluster/connection as
triage_graph.py's checkpointer (same MONGODB_URI env var), in a new
collection ("priority_score_history") inside the same "proauth_langgraph"
database — deliberately not the checkpointer abstraction itself, which is
built for "resume a single expensive per-thread computation," not "log a
batch ranking result over time." A queue-wide re-rank has no single
thread_id to key a checkpoint by, and there's nothing expensive here to
resume anyway (see priority_intelligence/README.md's MongoDB section for
the full reasoning).

Write-only from the rerank path's perspective (one document per case, per
rerank call) — this is what lets a future nurse dashboard feature show
"this case's priority has been climbing" by comparing a case's own recent
entries. get_recent_history() below is the read side of that, not yet
wired into any UI — logging has to run for a while before there's
anything meaningful to show a trend from.

Never blocks or fails a rerank response: a Mongo outage degrades to
"history not logged this time," never a 500 on the actual ranking
feature — same precedent as triageRoutes.js's own persistence try/except
around TriageEvaluation.create().
"""
import os
from datetime import datetime, timezone

from pymongo import MongoClient

DB_NAME = "proauth_langgraph"
COLLECTION_NAME = "priority_score_history"

_client = None


def _get_collection():
    global _client
    if _client is None:
        mongodb_uri = os.environ.get("MONGODB_URI")
        if not mongodb_uri:
            return None
        _client = MongoClient(mongodb_uri)
    return _client[DB_NAME][COLLECTION_NAME]


def log_priority_snapshot(ranked_records):
    """
    ranked_records: list of dicts from the ranked/tiered DataFrame (each
    has 'request_id', 'priority_score', 'priority_tier', 'queue_rank').
    Never raises.
    """
    try:
        collection = _get_collection()
        if collection is None or not ranked_records:
            return
        now = datetime.now(timezone.utc)
        documents = [
            {
                "authorizationId": record.get("request_id"),
                "timestamp": now,
                "priorityScore": record.get("priority_score"),
                "priorityTier": record.get("priority_tier"),
                "queueRank": record.get("queue_rank"),
            }
            for record in ranked_records
        ]
        collection.insert_many(documents, ordered=False)
    except Exception as exc:  # noqa: BLE001 - logging must never break ranking
        print(f"[priority_intelligence.history] Failed to log priority snapshot: {exc}")


def get_recent_history(authorization_id, limit=10):
    """
    Most recent logged snapshots for one authorization, newest first.
    Returns [] on any failure (missing MONGODB_URI, connection issue) —
    same "a history miss just means no trend to show, never an error"
    precedent as the write side above. Not yet called from any route;
    exists as the building block for a future "priority climbing" widget.
    """
    try:
        collection = _get_collection()
        if collection is None:
            return []
        cursor = collection.find(
            {"authorizationId": authorization_id},
            {"_id": 0},
        ).sort("timestamp", -1).limit(limit)
        return list(cursor)
    except Exception:
        return []
