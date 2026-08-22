import pandas as pd
from priority_intelligence import config
from priority_intelligence.ranker import PriorityRanker
from priority_intelligence.safety import apply_safety_overrides

def test_training_dataset_is_pend_only():
    df=pd.read_csv(config.TRAINING_SET_PATH)
    assert set(df.outcome.unique())=={'PEND'}

def test_ranker_rejects_more_information():
    df=pd.read_csv(config.QUEUE_SNAPSHOT_PATH).head(1)
    df.loc[0,'outcome']='MORE_INFORMATION'
    try: PriorityRanker().rank(df,'2026-08-20 09:00:00')
    except ValueError: return
    raise AssertionError('MORE_INFORMATION must never enter the priority ranker')

def test_emergency_override():
    df=pd.read_csv(config.QUEUE_SNAPSHOT_PATH).head(1)
    df.loc[0,'urgency']='emergency'; df.loc[0,'submitted_at']='2026-08-20 08:59:00'
    ranked=PriorityRanker().rank(df,'2026-08-20 09:00:00')
    ranked=apply_safety_overrides(ranked)
    assert ranked.iloc[0].priority_score >= 90
