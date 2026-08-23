import { ArrowUpRight, Check, CircleHelp, Clock3 } from 'lucide-react';
import { Badge, Card } from '../ui';

const decisionIcons = { clock: Clock3, check: Check, help: CircleHelp };

function Score({ label, value, color }) { return <div className="score"><div><span>{label}</span><b>{value}%</b></div><i><em style={{ width: value + '%', background: color }} /></i></div>; }

export default function AuthorizationDetail({ request }) {
  const r = request.resultDetail;
  if (!r) return null;
  const DecisionIcon = decisionIcons[r.icon] || Clock3;

  return <>
    <div className="decision-banner">
      <div className="decision-icon"><DecisionIcon size={28} /></div>
      <div><p>RECOMMENDED NEXT STEP</p><h2>{r.headline}</h2><span>{r.headlineNote}</span></div>
      <div className="model-score"><small>Model confidence</small><strong>{request.confidence}</strong><span>{r.modelInvoked ? 'Not medical certainty' : 'Deterministic gate — model not invoked'}</span></div>
    </div>
    <div className="result-grid">
      <div className="main-result">
        <Card>
          <div className="section-title"><div><p className="eyebrow">EXPLAINABLE DECISION</p><h3>Why this recommendation?</h3></div><Badge type={r.reviewBadgeTone}>{r.reviewBadge}</Badge></div>
          <p className="body-copy">{r.whyText}</p>
          <ul className="reason-list">{r.reasons.map(([tone, text, tag]) => <li key={text}><span className={`check ${tone}`}>{tone === 'amber' ? <CircleHelp size={14} /> : <Check size={14} />}</span>{text} <a>{tag}</a></li>)}</ul>
        </Card>
        <Card>
          <div className="section-title"><div><p className="eyebrow">POLICY COMPLIANCE</p><h3>Criteria evaluation</h3></div><strong className="compliance">{r.complianceScore}<small>/100</small></strong></div>
          {r.criteria.map(([label, result, tone]) => <div className="criteria" key={label}><span className={`dot ${tone}`}></span><span>{label}</span><Badge type={tone}>{result}</Badge></div>)}
        </Card>
      </div>
      <aside className="result-side">
        <Card><p className="eyebrow">TRIAGE DISTRIBUTION</p><h3>Model confidence</h3>
          {r.modelInvoked ? <>
            <Score label="Approve" value={r.distribution.approve} color="#78b69e" />
            <Score label="Nurse review" value={r.distribution.nurseReview} color="#477fb9" />
            <Score label="More information" value={r.distribution.moreInfo} color="#d3a140" />
            <p className="hint">A model signal, not a final clinical or coverage decision.</p>
          </> : <p className="body-copy">The ML model was not invoked for this request — a deterministic gate produced the outcome directly, so there is no model probability to show.</p>}
        </Card>
        <Card><p className="eyebrow">MISSING INFORMATION</p><h3>Evidence to consider</h3>
          {r.missingEvidenceText ? <><div className="missing"><CircleHelp size={16} /><span>{r.missingEvidenceText}</span></div><button className="button full">View required evidence</button></> : <p className="body-copy">No outstanding evidence is required for this request.</p>}
        </Card>
      </aside>
    </div>
    <div className="lower-grid">
      <Card>
        <div className="section-title"><div><p className="eyebrow">RETRIEVED POLICY EVIDENCE</p><h3>Policy intelligence</h3></div><Badge>RAG retrieval</Badge></div>
        <div className="policy-meta"><span><b>Policy</b>{r.policyEvidence.name}</span><span><b>Type</b>{r.policyEvidence.type}</span><span><b>Effective</b>{r.policyEvidence.effective}</span></div>
        <div className="evidence-quote"><span>01</span><div><strong>Coverage criteria · Relevant summary</strong><p>{r.policyEvidence.summary}</p><small>Relevance {r.policyEvidence.relevance}% · Policy retrieval service</small></div></div>
        <button className="text-button">View policy source <ArrowUpRight size={14} /></button>
      </Card>
      <Card><p className="eyebrow">AI WORKBENCH</p><h3>Processing activity</h3>
        {r.workbench.map(([agent, detail], i) => <div className="agent-row" key={agent}><span><Check size={13} /></span><div><strong>{agent}</strong><small>{detail}</small></div>{i === r.workbench.length - 1 && <Badge type="blue">{request.confidence}</Badge>}</div>)}
      </Card>
    </div>
  </>;
}
