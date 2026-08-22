# Validates the adapted priority agent against REAL data pulled live from
# our own Postgres (2026-08-21) — 12 actual "Needs Review" authorizations,
# each joined to its most recent TriageEvaluation row for the real
# policy_score/documentation_score/clinical_evidence_score/
# numCriteriaMissing our own coverage_reasoning_agent.py already computes.
# Deliberately kept AS-EXTRACTED, including the blank urgency/care_setting
# most of these real rows actually have — that's the exact gap
# features.py's normalization is supposed to cover, not a scrubbed/ideal
# fixture.
from pathlib import Path

import pandas as pd

from ..agent.graph import build_priority_graph

SAMPLE_PATH = Path(__file__).resolve().parent / 'real_pend_sample.csv'


def _load_real_cases():
    df = pd.read_csv(SAMPLE_PATH, dtype={'urgency': str, 'care_setting': str})
    df['outcome'] = 'PEND'
    return df


def test_real_cases_all_produce_a_rank_and_tier():
    df = _load_real_cases()
    app = build_priority_graph()
    result = app.invoke({'cases': df.to_dict('records'), 'now': '2026-08-21 09:00:00'})
    ranked = result['ranked_cases']
    assert len(ranked) == len(df)
    for case in ranked:
        assert case['priority_tier'] in ('HIGH', 'MEDIUM', 'LOW')
        assert 1 <= case['queue_rank'] <= len(df)
        assert 0 <= case['priority_score'] <= 100


def test_blank_urgency_and_care_setting_do_not_produce_nan():
    # 8 of the 12 real rows have blank urgency AND blank care_setting —
    # confirmed live against the DB. Before the features.py fix, these
    # silently became NaN through .map() and corrupted every downstream
    # derived feature for those rows.
    df = _load_real_cases()
    app = build_priority_graph()
    result = app.invoke({'cases': df.to_dict('records'), 'now': '2026-08-21 09:00:00'})
    for case in result['ranked_cases']:
        assert pd.notna(case['priority_score'])
        assert pd.notna(case['ml_priority_score'])


def test_queue_is_sorted_highest_priority_first():
    df = _load_real_cases()
    app = build_priority_graph()
    result = app.invoke({'cases': df.to_dict('records'), 'now': '2026-08-21 09:00:00'})
    scores = [case['priority_score'] for case in result['ranked_cases']]
    assert scores == sorted(scores, reverse=True)


def test_mixed_severity_queue_produces_all_three_tiers():
    # All 12 real cases are genuinely low-urgency right now (none emergency,
    # none close to SLA breach) — on their own they only ever produce LOW,
    # which by itself doesn't prove HIGH/MEDIUM classification works at
    # all. Mixing in one clear emergency case and one clear "urgent, poor
    # evidence, not yet breached" case alongside the real queue is what
    # actually exercises all three tiers together, the way a real mixed
    # nurse queue would.
    df = _load_real_cases()
    synthetic = pd.DataFrame([
        {'request_id': 'SYNTH-EMERGENCY', 'outcome': 'PEND', 'policy_score': 60, 'documentation_score': 70,
         'clinical_evidence_score': 70, 'num_criteria_missing': 0, 'urgency': 'Emergency',
         'care_setting': 'Emergency Department', 'submitted_at': '2026-08-21 07:00:00'},
        {'request_id': 'SYNTH-URGENT-POOR-EVIDENCE', 'outcome': 'PEND', 'policy_score': 15, 'documentation_score': 10,
         'clinical_evidence_score': 10, 'num_criteria_missing': 4, 'urgency': 'Urgent',
         'care_setting': 'Inpatient', 'submitted_at': '2026-08-20 15:00:00'},
    ])
    combined = pd.concat([df, synthetic], ignore_index=True)
    app = build_priority_graph()
    result = app.invoke({'cases': combined.to_dict('records'), 'now': '2026-08-21 09:00:00'})
    tiers_seen = {case['priority_tier'] for case in result['ranked_cases']}
    assert tiers_seen == {'HIGH', 'MEDIUM', 'LOW'}
    by_id = {case['request_id']: case for case in result['ranked_cases']}
    assert by_id['SYNTH-EMERGENCY']['priority_tier'] == 'HIGH'
    assert by_id['SYNTH-EMERGENCY']['queue_rank'] == 1  # emergency must always sort first
    assert by_id['SYNTH-URGENT-POOR-EVIDENCE']['priority_tier'] == 'MEDIUM'
