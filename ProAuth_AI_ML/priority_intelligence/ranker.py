import json
import joblib
import pandas as pd
from . import config
from .features import RANKER_FEATURES,compute_dynamic_features

# XGBRanker (rank:ndcg) outputs a raw relevance score, NOT a 0-100 scale —
# verified empirically (2026-08-21) against both the source package's own
# synthetic sample and 12 real PEND cases pulled live from our database:
# observed range roughly [-3.7, +3.3]. safety.py's np.maximum(score, 0)
# floor previously applied straight to this raw score, which meant EVERY
# case that didn't trip a safety override collapsed to exactly 0 — the
# model's real (if narrow-band) differentiation between cases was being
# destroyed before priority_tier ever saw it, making a genuine MEDIUM tier
# unreachable in practice. RAW_SCORE_MIN/MAX below are fixed, not
# batch-relative percentiles — deliberately, so a case's tier means the
# same thing regardless of what else happens to be in the queue that day,
# rather than a small queue artificially stretching two routine cases to
# 0 and 100. Bounds carry headroom beyond every value observed so far.
RAW_SCORE_MIN=-4.0
RAW_SCORE_MAX=4.0

def _rescale_to_0_100(raw_scores):
    clipped=raw_scores.clip(RAW_SCORE_MIN,RAW_SCORE_MAX)
    return (clipped-RAW_SCORE_MIN)/(RAW_SCORE_MAX-RAW_SCORE_MIN)*100

class PriorityRanker:
    def __init__(self, model_path=config.RANKER_PATH):
        self.model=joblib.load(model_path)
        self.metadata=json.loads(config.RANKER_METADATA_PATH.read_text())
        if self.metadata.get('source_filter') != "outcome == 'PEND' ONLY":
            raise RuntimeError('Refusing to load a ranker not trained on PEND-only data.')
    def rank(self, cases, now):
        if not len(cases): return cases.copy()
        cases=cases.copy()
        if 'outcome' in cases and not cases['outcome'].eq('PEND').all():
            raise ValueError('Priority ranker accepts PEND cases only.')
        cases=compute_dynamic_features(cases,now)
        # ml_priority_score: the raw XGBRanker output, kept as-is for
        # transparency/debugging. ml_priority_score_scaled: the 0-100
        # rescale safety.py actually builds priority_score from.
        cases['ml_priority_score']=self.model.predict(cases[RANKER_FEATURES])
        cases['ml_priority_score_scaled']=_rescale_to_0_100(cases['ml_priority_score'])
        return cases

# Module-level singleton, loaded once (2026-08-21+) — NOT just an
# efficiency win. Verified empirically: unpickling this XGBoost model
# AFTER sentence_transformers/torch (rag/retrieval.py's embedding model)
# has already been imported into the same process causes a hard SIGSEGV
# with zero Python-level error output — both libraries bundle their own
# native OpenMP runtime, and whichever initializes first "wins"; loading
# XGBoost second consistently crashed in reproduction, loading it first
# consistently worked. The old per-request `PriorityRanker()` in
# api/main.py's route handler created a fresh instance long after
# rag.retrieval was already imported at process startup — every real
# request would have crashed the whole service. get_ranker() below MUST
# be called once, eagerly, before rag.retrieval is imported anywhere —
# see policy-rag/main.py's import order, and priority_intelligence/
# README.md's "known issue" section.
_ranker_singleton=None

def get_ranker():
    global _ranker_singleton
    if _ranker_singleton is None:
        _ranker_singleton=PriorityRanker()
    return _ranker_singleton
