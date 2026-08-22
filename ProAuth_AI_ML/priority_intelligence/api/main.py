"""
FastAPI router for the priority-intelligence feature. An APIRouter, not
its own FastAPI() app (2026-08-21+) — mounted onto the existing
policy-rag main.py's app rather than run as a second Python process, so
there's one service to run/manage instead of two. See
priority_intelligence/README.md.
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
import pandas as pd
from ..ranker import get_ranker
from ..safety import apply_safety_overrides
from ..explanations import explain
from ..tiers import add_priority_tier
from ..history import log_priority_snapshot

router = APIRouter()


class RerankRequest(BaseModel):
    cases: list[dict[str, Any]]
    now: str | None = None


@router.get('/priority/health')
def health():
    return {'status': 'ok', 'scope': 'PEND-only'}


@router.post('/priority/rerank')
def rerank(req: RerankRequest):
    try:
        df = pd.DataFrame(req.cases)
        if df.empty:
            return {'cases': []}
        if 'outcome' in df.columns and not df['outcome'].eq('PEND').all():
            raise ValueError('Only PEND cases are accepted.')
        ranked = get_ranker().rank(df, pd.Timestamp(req.now or datetime.now().isoformat()))
        ranked = apply_safety_overrides(ranked)
        ranked = add_priority_tier(ranked)
        ranked['priority_reason_codes'] = ranked.apply(explain, axis=1)
        ranked['queue_rank'] = range(1, len(ranked) + 1)
        records = ranked.to_dict('records')
        # Logging never blocks or fails this response — see history.py.
        log_priority_snapshot(records)
        return {'cases': records}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001 - same defensive backstop precedent as main.py's /triage
        raise HTTPException(status_code=503, detail=f'Priority ranking failed unexpectedly: {e}')
