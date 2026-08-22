import numpy as np
import pandas as pd
from . import config

RANKER_FEATURES=[
    'policy_score','documentation_score','clinical_evidence_score','num_criteria_missing',
    'hours_pending','sla_pressure','urgency_weight','care_setting_weight','clinical_risk_weight'
]
_RISK_WEIGHT={'LOW':1.0,'MODERATE':1.6,'HIGH':2.3,'CRITICAL':3.0}

def _clinical_risk_tier(row):
    evidence=float(row['clinical_evidence_score']); missing=int(row['num_criteria_missing']); urgency=row['urgency']
    if urgency=='emergency': return 'CRITICAL'
    if evidence<50 or missing>=3: return 'HIGH'
    if evidence<75 or missing>=1: return 'MODERATE'
    return 'LOW'

def _normalize_urgency(series):
    # Our real system stores urgency capitalized ('Routine'/'Urgent'/
    # 'Emergency' — ProAuth_AI_FrontEnd's NewAuthorization.jsx Treatment
    # step) while SLA_HOURS_BY_URGENCY/URGENCY_WEIGHT are keyed lowercase.
    # A raw case with the wrong case (or blank/unset — real, found in our
    # DB: several historical authorizations have no urgency recorded at
    # all) previously fell straight through .map() to NaN with no error,
    # silently corrupting every downstream derived feature. Unknown/blank
    # defaults to 'routine' — the least-urgent, most conservative
    # assumption, never inflating a case's priority from a missing value.
    normalized = series.astype(str).str.strip().str.lower()
    return normalized.where(normalized.isin(config.SLA_HOURS_BY_URGENCY.keys()), 'routine')

def _normalize_care_setting(series):
    # Our wizard only offers 'Outpatient'/'Inpatient' today (a subset of
    # CARE_SETTING_WEIGHT's 4 values, matching case already) — this guards
    # blank/unrecognized values the same conservative way as urgency above,
    # defaulting to 'Outpatient' (the lowest care-setting weight) rather
    # than silently producing NaN.
    stripped = series.astype(str).str.strip()
    return stripped.where(stripped.isin(config.CARE_SETTING_WEIGHT.keys()), 'Outpatient')

def compute_dynamic_features(df, now):
    df=df.copy()
    df['urgency']=_normalize_urgency(df['urgency'])
    df['care_setting']=_normalize_care_setting(df['care_setting'])
    # Real submitted_at values from our own Postgres come through
    # timezone-AWARE (Authorization.submittedAt is TIMESTAMPTZ, serialized
    # with a UTC offset) — the source package's own convention (its
    # synthetic CSVs, its `now` default) is timezone-NAIVE, and pandas
    # refuses to subtract a tz-aware datetime from a tz-naive one at all
    # (raises, doesn't silently miscompute). Normalizing both to naive UTC
    # here means this works with either real or synthetic input without
    # the caller needing to know or care which.
    submitted=pd.to_datetime(df['submitted_at'], format='mixed', utc=True).dt.tz_localize(None)
    now=pd.Timestamp(now)
    if now.tzinfo is not None:
        now=now.tz_convert('UTC').tz_localize(None)
    df['hours_pending']=(now-submitted).dt.total_seconds()/3600
    df['sla_deadline_hours']=df['urgency'].map(config.SLA_HOURS_BY_URGENCY).astype(float)
    df['hours_to_breach']=df['sla_deadline_hours']-df['hours_pending']
    df['sla_pressure']=(df['hours_pending']/df['sla_deadline_hours']*100).clip(lower=0)
    df['urgency_weight']=df['urgency'].map(config.URGENCY_WEIGHT).astype(float)
    df['care_setting_weight']=df['care_setting'].map(config.CARE_SETTING_WEIGHT).astype(float)
    df['clinical_risk_tier']=df.apply(_clinical_risk_tier,axis=1)
    df['clinical_risk_weight']=df['clinical_risk_tier'].map(_RISK_WEIGHT).astype(float)
    df['is_sla_breach_imminent']=df['hours_to_breach']<=config.SLA_BREACH_OVERRIDE_HOURS
    df['is_sla_breached']=df['hours_to_breach']<0
    df['is_emergency']=df['urgency'].eq('emergency')
    return df

def composite_score(row):
    sla=min(float(row['sla_pressure']),150)/150*100
    urgency=(float(row['urgency_weight'])-1)/2*100
    risk=(float(row['clinical_risk_weight'])-1)/2*100
    gap=(100-float(row['documentation_score']))*.5+(100-float(row['clinical_evidence_score']))*.5
    return float(np.clip(.40*sla+.20*urgency+.20*risk+.20*gap,0,100))
