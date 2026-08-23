import { useEffect, useState } from 'react';
import { ChevronDown, ChevronLeft, ChevronRight, FileText, Search, ShieldCheck } from 'lucide-react';
import AppLayout from '../components/layout/AppLayout';
import { Badge, Card, DataState } from '../components/ui';
import { policyApi } from '../services/policyApi';
import { insurancePlanApi } from '../services/insurancePlanApi';

function toneForStatus(status) {
  if (status === 'ACTIVE') return 'green';
  if (status === 'RETIRED' || status === 'INACTIVE') return 'amber';
  return 'blue';
}

// The union every Private-tier plan retrieves against — Silver/Gold/Premium
// share the SAME underlying policy corpus (see rag/retrieval.py's
// PRIVATE_PAYER_GROUP); the tiers differ by cost-share, not by which
// policies apply. TIER_COST_SHARE_PERCENT mirrors that same file's
// TIER_COST_SHARE_PERCENT exactly — a real value already used in triage
// explanations, not invented for this page. Medicare has no equivalent
// figure anywhere in the system (deliberately — see that file's comments).
const PRIVATE_PAYERS = ['Aetna', 'Cigna', 'UnitedHealthcare'];
const TIER_COST_SHARE_PERCENT = { SILVER: 60, GOLD: 80, PREMIUM: 95 };

function payerScopeFor(plan) {
  return plan.coverageType === 'MEDICARE' ? ['Medicare'] : PRIVATE_PAYERS;
}

function PolicyDetail({ policyId }) {
  const [detail, setDetail] = useState(null);
  const [status, setStatus] = useState('loading');

  useEffect(() => {
    let cancelled = false;
    setStatus('loading');
    policyApi.getById(policyId)
      .then(data => { if (!cancelled) { setDetail(data); setStatus('done'); } })
      .catch(() => { if (!cancelled) { setStatus('error'); setDetail(null); } });
    return () => { cancelled = true; };
  }, [policyId]);

  if (status === 'loading') return <div className="policy-detail-panel"><DataState status="loading"/></div>;
  if (status === 'error' || !detail) return <div className="policy-detail-panel"><p className="body-copy">Couldn't load this policy's detail.</p></div>;

  const versions = detail.versions || [];
  const criteria = detail.criteria || [];

  return <div className="policy-detail-panel">
    <div className="policy-meta">
      <span><b>Source</b>{detail.source}</span>
      <span><b>Policy type</b>{detail.policyType || 'Not specified'}</span>
      <span><b>Effective date</b>{detail.effectiveDate || 'Not specified'}</span>
      <span><b>Document path</b>{detail.documentPath || 'Not specified'}</span>
    </div>
    {versions.length > 0 && <><p className="hint" style={{ marginTop: 12 }}>VERSIONS</p>{versions.map(v => <div className="criteria" key={v.id}><span>{v.version}</span><span>{v.effectiveDate || '—'} – {v.expirationDate || 'present'}</span></div>)}</>}
    <p className="hint" style={{ marginTop: 12 }}>CRITERIA ({criteria.length})</p>
    {criteria.length ? criteria.map(c => <div className="criteria" key={c.id}><span className={`dot ${c.requirement === 'REQUIRED' ? 'amber' : 'blue'}`}></span><span>{c.criterionText}</span><Badge type={c.requirement === 'REQUIRED' ? 'amber' : 'blue'}>{c.requirement || c.criterionType || 'INFO'}</Badge></div>) : <p className="body-copy">No structured criteria recorded for this policy.</p>}
  </div>;
}

function PlanOverviewCard({ plan, policyCount, onOpen }) {
  const scope = payerScopeFor(plan);
  return <Card className="pipeline">
    <div className="section-title"><div><p className="eyebrow">{plan.coverageType}</p><h3>{plan.planName}</h3></div><Badge type="blue">{policyCount} polic{policyCount === 1 ? 'y' : 'ies'}</Badge></div>
    <div className="policy-meta"><span><b>Payer</b>{scope.join(', ')}</span><span><b>Jurisdiction</b>{plan.jurisdiction || 'US'}</span></div>
    {plan.tier
      ? <div className="evidence-quote"><span><ShieldCheck size={15}/></span><div><strong>Estimated cost-share: {TIER_COST_SHARE_PERCENT[plan.tier]}%</strong><p>This plan is estimated to cover about {TIER_COST_SHARE_PERCENT[plan.tier]}% of the allowed expense — you're responsible for the remainder. A general estimate, not looked up from a specific benefit document.</p></div></div>
      : <div className="evidence-quote"><span><ShieldCheck size={15}/></span><div><strong>Medicare coverage</strong><p>Coverage is evaluated against real CMS National Coverage Determinations (NCDs) — the same public, cited criteria Medicare itself publishes.</p></div></div>}
    <button className="button full" type="button" onClick={onOpen} style={{ marginTop: 14 }}>View {policyCount} polic{policyCount === 1 ? 'y' : 'ies'} <ChevronRight size={16}/></button>
  </Card>;
}

export default function Policies() {
  const [plans, setPlans] = useState([]);
  const [plansStatus, setPlansStatus] = useState('loading');
  const [policies, setPolicies] = useState([]);
  const [policiesStatus, setPoliciesStatus] = useState('loading');
  const [error, setError] = useState('');
  const [selectedPlanId, setSelectedPlanId] = useState(null);
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    let cancelled = false;
    insurancePlanApi.listActive()
      .then(list => { if (!cancelled) { setPlans(list); setPlansStatus('done'); } })
      .catch(err => { if (!cancelled) { setError(err.message || 'Failed to load plans.'); setPlansStatus('error'); } });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    policyApi.list()
      .then(list => { if (!cancelled) { setPolicies(list); setPoliciesStatus('done'); } })
      .catch(err => { if (!cancelled) { setError(err.message || 'Failed to load policies.'); setPoliciesStatus('error'); } });
    return () => { cancelled = true; };
  }, []);

  if (plansStatus !== 'done' || policiesStatus !== 'done') {
    return <AppLayout><div className="page dashboard"><div className="page-heading"><div><h1>Policy explorer</h1></div></div><DataState status={plansStatus === 'error' || policiesStatus === 'error' ? 'error' : 'loading'} error={error}/></div></AppLayout>;
  }

  const selectedPlan = plans.find(p => p.planId === selectedPlanId);

  if (!selectedPlan) {
    return <AppLayout><div className="page dashboard">
      <div className="page-heading"><div><p className="eyebrow">POLICY EXPLORER</p><h1>Coverage plans</h1><p>The {plans.length} real coverage plans this system evaluates requests against, and what each one covers.</p></div></div>
      <div className="analytics-grid">
        {plans.map(plan => <PlanOverviewCard key={plan.planId} plan={plan} policyCount={policies.filter(p => payerScopeFor(plan).includes(p.payerName)).length} onOpen={() => setSelectedPlanId(plan.planId)}/>)}
      </div>
    </div></AppLayout>;
  }

  const scope = payerScopeFor(selectedPlan);
  const visible = policies.filter(p => scope.includes(p.payerName) && (!search || [p.policyName, p.policyId].some(field => field?.toLowerCase().includes(search.toLowerCase()))));

  return <AppLayout><div className="page simple">
    <button className="text-button" type="button" onClick={() => { setSelectedPlanId(null); setSearch(''); setExpanded(null); }}><ChevronLeft size={15}/>Back to plans</button>
    <h1>{selectedPlan.planName}</h1>
    <p className="lead">{visible.length} of {policies.filter(p => scope.includes(p.payerName)).length} real, ingested policies for {scope.join(', ')}.</p>
    <Card>
      <div className="table-tools">
        <div className="search small"><Search size={16}/><input placeholder="Search policy name or ID…" aria-label="Search policies" value={search} onChange={e => setSearch(e.target.value)}/></div>
      </div>
      <div className="request-table">
        <div className="thead" style={{ gridTemplateColumns: '1fr 2.6fr 1fr .8fr .7fr 30px' }}><span>Policy ID</span><span>Policy name</span><span>Payer</span><span>Source</span><span>Status</span><span></span></div>
        {visible.map(policy => <div key={policy.id}>
          <div className="trow" style={{ gridTemplateColumns: '1fr 2.6fr 1fr .8fr .7fr 30px', cursor: 'pointer' }} role="button" tabIndex={0} onClick={() => setExpanded(expanded === policy.id ? null : policy.id)} onKeyDown={e => e.key === 'Enter' && setExpanded(expanded === policy.id ? null : policy.id)}>
            <strong>{policy.policyId}</strong>
            <span className="truncate-cell" title={policy.policyName}>{policy.policyName}</span>
            <span>{policy.payerName || '—'}</span>
            <span>{policy.source}</span>
            <Badge type={toneForStatus(policy.status)}>{policy.status}</Badge>
            {expanded === policy.id ? <ChevronDown size={16}/> : <ChevronRight size={16}/>}
          </div>
          {expanded === policy.id && <PolicyDetail policyId={policy.id}/>}
        </div>)}
        {visible.length === 0 && <div className="empty"><FileText size={27}/><h3>No policies match this search</h3><p>Try a different search term.</p></div>}
      </div>
    </Card>
  </div></AppLayout>;
}
