from typing import TypedDict,Any
import pandas as pd
from ..ranker import get_ranker
from ..safety import apply_safety_overrides
from ..explanations import explain
from ..tiers import add_priority_tier

class PriorityState(TypedDict, total=False):
    cases: list[dict]
    now: str
    ranked_cases: list[dict]

def build_priority_graph():
    from langgraph.graph import StateGraph,START,END
    def validate(state):
        df=pd.DataFrame(state['cases'])
        if df.empty: return {'cases': []}
        if 'outcome' in df.columns and not df['outcome'].eq('PEND').all():
            raise ValueError('Only PEND cases may enter the nurse priority agent.')
        required=['request_id','policy_score','documentation_score','clinical_evidence_score','num_criteria_missing','urgency','care_setting','submitted_at']
        missing=[c for c in required if c not in df.columns]
        if missing: raise ValueError(f'Missing required priority fields: {missing}')
        return {'cases':df.to_dict('records')}
    def rank(state):
        df=pd.DataFrame(state['cases']);
        if df.empty: return {'ranked_cases': []}
        ranked=get_ranker().rank(df,pd.Timestamp(state['now']))
        ranked=apply_safety_overrides(ranked)
        ranked=add_priority_tier(ranked)
        ranked['priority_reason_codes']=ranked.apply(explain,axis=1)
        ranked['queue_rank']=range(1,len(ranked)+1)
        return {'ranked_cases':ranked.to_dict('records')}
    g=StateGraph(PriorityState); g.add_node('validate',validate); g.add_node('rank',rank); g.add_edge(START,'validate'); g.add_edge('validate','rank'); g.add_edge('rank',END); return g.compile()
