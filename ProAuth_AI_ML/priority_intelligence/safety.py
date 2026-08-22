import numpy as np

def apply_safety_overrides(df):
    # Built from ml_priority_score_scaled (0-100), not the raw
    # ml_priority_score — see ranker.py's docstring. Using the raw score
    # here meant np.maximum(score, 0) floored every non-overridden case to
    # exactly 0, destroying the model's real (if narrow) differentiation
    # between them before it could ever reach a tier decision.
    df=df.copy(); score=df['ml_priority_score_scaled'].astype(float).to_numpy()
    score=np.maximum(score, np.where(df['is_emergency'],90,0))
    score=np.maximum(score, np.where(df['is_sla_breached'],88,0))
    score=np.maximum(score, np.where(df['is_sla_breach_imminent'],80,0))
    df['priority_score']=np.clip(score,0,100)
    df['safety_override']=df['priority_score']>df['ml_priority_score_scaled']
    return df.sort_values(['priority_score','hours_pending'],ascending=[False,False]).reset_index(drop=True)
