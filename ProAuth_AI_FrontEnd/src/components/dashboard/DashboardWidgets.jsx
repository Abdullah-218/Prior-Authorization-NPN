import React from 'react';
import { ArrowUpRight, Check } from 'lucide-react';
import { Card, Icon } from '../ui';

// `delta` renders with the "vs. yesterday" caption (a real day-over-day
// comparison). `note` is for a plain descriptive caption when no
// day-over-day figure exists — showing "vs. yesterday" next to a number
// that isn't one would be a fabricated comparison, not just decoration.
export function StatCard({ label, value, delta, note, icon, tone }) {
  return <Card className="stat"><div><p>{label}</p><h2>{value}</h2>{delta ? <><small className={tone}>{delta}</small><span className="vs">vs. yesterday</span></> : note ? <small className={tone}>{note}</small> : null}</div><Icon tone={tone}>{icon}</Icon></Card>;
}

export function DecisionPipeline({ pipeline = { completed: 126, inProgress: 2, currentStage: 'ML triage' } }) {
  const steps = ['Request', 'Policy retrieval', 'Evidence analysis', 'Criteria evaluation', 'ML triage', 'Decision'];
  const currentIndex = pipeline.currentStage ? Math.max(0, steps.indexOf(pipeline.currentStage)) : 4;
  return <Card className="pipeline"><div className="section-title"><div><p className="eyebrow">LIVE OPERATIONS</p><h3>Decision pipeline</h3></div><a>View methodology <ArrowUpRight size={14}/></a></div><div className="flow">{steps.map((step, index) => <React.Fragment key={step}><div className={`flow-step ${index === currentIndex ? 'current' : ''}`}><span>{index < currentIndex ? <Check size={14}/> : index + 1}</span><label>{step}</label></div>{index < 5 && <div className="flow-line"/>}</React.Fragment>)}</div><div className="pipeline-foot"><span><b>{pipeline.completed}</b> decisions completed today</span><span><i className="pulse"></i> {pipeline.inProgress} requests being analyzed</span></div></Card>;
}
