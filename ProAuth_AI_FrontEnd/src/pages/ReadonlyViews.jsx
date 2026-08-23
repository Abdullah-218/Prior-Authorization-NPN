import { lazy, Suspense, useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { Activity, BarChart3, Check, ChevronRight, Clock3, FileText, Search, ShieldCheck } from 'lucide-react';
import AppLayout from '../components/layout/AppLayout';

const HeroModel = lazy(() => import('../components/dashboard/HeroModel'));
import { Badge, Card, DataState } from '../components/ui';
import { DecisionPipeline, StatCard } from '../components/dashboard/DashboardWidgets';
import { authorizationService } from '../services/authorizationService';
import { policyService } from '../services/policyService';
import { useAuth } from '../hooks/useAuth';
import { useLiveRequests } from '../hooks/useLiveRequests';
import { useTriageDetail } from '../hooks/useTriageDetail';
import { useDocumentsForAuthorizations, mapDocumentsToTuples, mapDocumentsToRows } from '../hooks/useDocuments';
import AuthorizationDetail from '../components/authorization/AuthorizationDetail';
import DiagnosisSpotlight from '../components/patient/DiagnosisSpotlight';
import { DocumentRow } from '../components/documents/DocumentRow';

export function ReadonlyPolicyPage() {
  const policies = policyService.getReadonlyPolicies();
  const [query, setQuery] = useState('');
  const visiblePolicies = policies.filter(policy => `${policy.type} ${policy.area} ${policy.overview}`.toLowerCase().includes(query.toLowerCase()));
  return <AppLayout><div className="page dashboard"><div className="page-heading"><div><p className="eyebrow">POLICY EXPLORER</p><h1>Policy explorer</h1><p>Search and review policy coverage information available to your account.</p></div></div><div className="search small"><Search size={16}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search policy" aria-label="Search policy"/></div><div className="analytics-grid">{visiblePolicies.map(policy => <Card className="pipeline" key={policy.type}><div className="section-title"><div><p className="eyebrow">{policy.type}</p><h3>{policy.area}</h3></div><Badge type="green">{policy.status}</Badge></div><div className="policy-meta"><span><b>Policy type</b>{policy.type}</span><span><b>Coverage area</b>{policy.area}</span><span><b>Effective date</b>{policy.effective}</span></div><p className="body-copy">{policy.overview}</p><div className="criteria"><span className="dot green"></span><span>Coverage criteria</span><small>{policy.coverage}</small></div><div className="criteria"><span className="dot green"></span><span>Diagnosis criteria</span><small>{policy.diagnosis}</small></div><div className="criteria"><span className="dot blue"></span><span>Procedure criteria</span><small>{policy.procedure}</small></div><div className="criteria"><span className="dot amber"></span><span>Documentation requirements</span><small>{policy.documentation}</small></div><div className="evidence-quote"><span><ShieldCheck size={15}/></span><div><strong>Retrieved evidence</strong><p>{policy.evidence}</p></div></div></Card>)}</div></div></AppLayout>;
}

export function ReadonlyAnalyticsPage() {
  const metrics = authorizationService.getReadonlyAnalytics();
  return <AppLayout><div className="page simple"><p className="eyebrow">READ-ONLY ANALYTICS</p><h1>Authorization analytics</h1><p className="lead">View operational trends without reviewer actions or export controls.</p><div className="stat-grid"><StatCard label="Authorization volume" value={metrics.requestsToday} delta="Requests today" tone="blue" icon={<FileText size={20}/>}/><StatCard label="Approval rate" value="59.4%" delta="76 approved" tone="green" icon={<Check size={20}/>}/><StatCard label="Nurse review rate" value="24.2%" delta="31 requests" tone="blue" icon={<Clock3 size={20}/>}/><StatCard label="More information rate" value="16.4%" delta="21 requests" tone="amber" icon={<Activity size={20}/>}/></div><DecisionPipeline/><div className="analytics-grid"><Card><div className="section-title"><h3>Average processing time</h3><Badge type="blue">4m 12s</Badge></div><p className="body-copy">Average time from request intake to available triage summary.</p></Card><Card><div className="section-title"><h3>Policy distribution</h3><BarChart3 size={18}/></div><div className="criteria"><span>Medicare Advantage</span><Badge type="blue">42%</Badge></div><div className="criteria"><span>Commercial</span><Badge type="green">35%</Badge></div><div className="criteria"><span>Medicaid</span><Badge type="amber">23%</Badge></div></Card><Card><div className="section-title"><h3>Request type distribution</h3></div><div className="criteria"><span>Imaging</span><Badge type="blue">38%</Badge></div><div className="criteria"><span>Medication</span><Badge type="green">34%</Badge></div><div className="criteria"><span>Therapy</span><Badge type="amber">28%</Badge></div></Card><Card><div className="section-title"><h3>AI triage accuracy</h3><Badge type="green">91%</Badge></div><p className="body-copy">Read-only model performance summary.</p></Card><Card><div className="section-title"><h3>Model confidence distribution</h3></div><div className="criteria"><span>High confidence</span><Badge type="green">68%</Badge></div><div className="criteria"><span>Review range</span><Badge type="blue">24%</Badge></div><div className="criteria"><span>Low confidence</span><Badge type="amber">8%</Badge></div></Card><Card><div className="section-title"><h3>Human override rate</h3><Badge type="blue">7.2%</Badge></div><p className="body-copy">Summary only. Reviewer actions are not exposed to this role.</p></Card></div></div></AppLayout>;
}

export function ReadonlyDashboard({ user }) {
  const navigate = useNavigate();
  const { status: listStatus, error: listError } = useLiveRequests();
  const summary = listStatus === 'done' ? authorizationService.getReadonlySummary() : null;
  const record = summary?.requests[0] || null;
  const { documentsByAuthorization } = useDocumentsForAuthorizations(record ? [record.id] : []);

  if (listStatus !== 'done') return <AppLayout><div className="page simple"><DataState status={listStatus} error={listError}/></div></AppLayout>;
  if (!record) return <AppLayout><div className="page simple"><div className="page-heading role-hero-heading"><div><p className="role-hero-eyebrow">MEMBER PORTAL</p><h1>Welcome, {user.name}</h1><p className="role-hero-sub">View your authorization requests and their current status.</p></div><Suspense fallback={<div className="hero-model"/>}><HeroModel/></Suspense></div><Card className="empty"><ShieldCheck size={27}/><h3>No authorization requests yet</h3><p>Requests filed on your behalf will appear here.</p></Card></div></AppLayout>;

  const documents = mapDocumentsToTuples(documentsByAuthorization[record.id]);

  return <AppLayout><div className="page simple"><div className="page-heading role-hero-heading"><div><p className="role-hero-eyebrow">MEMBER PORTAL</p><h1>Welcome, {user.name}</h1><p className="role-hero-sub">View your authorization requests and their current status.</p></div><Suspense fallback={<div className="hero-model"/>}><HeroModel/></Suspense></div><Card className="readonly-details"><div className="section-title"><div><p className="eyebrow">USER PROFILE</p><h3>{user.name}</h3></div></div><div className="policy-meta"><span><b>Name</b>{user.name}</span><span><b>Email</b>{user.email}</span><span><b>User ID</b>{user.id}</span><span><b>Patient ID</b>{record.patientId}</span><span><b>Member ID</b>{record.memberId}</span><span><b>Age / Sex</b>{record.age} / {record.sex}</span><span><b>Date of birth</b>{record.dateOfBirth}</span><span><b>Plan name</b>{record.planName}</span><span><b>Plan ID</b>{record.planId}</span><span><b>Coverage status</b>{record.coverageStatus}</span></div><div className="criteria"><span className="dot blue"></span><span>Policy</span><small>{record.policyName} · {record.policyId} · {record.policyType} · {record.coverageStatus}</small></div><div className="criteria"><span className="dot green"></span><span>Diagnosis</span><small>{record.diagnosis} ({record.icd10}) · Secondary: {record.secondaryDiagnoses}</small></div><div className="criteria"><span className="dot green"></span><span>Clinical history</span><small>{record.clinicalHistory}</small></div><div className="criteria"><span className="dot blue"></span><span>Most recent request</span><small>{record.service} · Code {record.procedureCode} · {record.urgency} · {record.careSetting}</small></div><div className="criteria"><span className="dot amber"></span><span>Status</span><small>{record.status} · Submitted {record.date} · Updated {record.lastUpdated}</small></div><div className="evidence-quote"><span><ShieldCheck size={15}/></span><div><strong>Decision: {record.decision}</strong><p>{record.decisionExplanation}</p>{record.missingInformation && <small>Missing information: {record.missingInformation}</small>}</div></div><div className="criteria"><span className="dot blue"></span><span>Documents</span><small>{documents.length ? documents.map(([name, status]) => `${name} (${status})`).join(' · ') : 'None on file'}</small></div><div className="criteria"><span className="dot green"></span><span>Timeline</span><small>{record.timeline.join(' → ')}</small></div></Card>

    <Card className="auth-history-card"><div className="section-title"><div><p className="eyebrow">AUTHORIZATION HISTORY</p><h3>All your requests</h3></div><Badge type="blue">{summary.requests.length} request{summary.requests.length === 1 ? '' : 's'}</Badge></div>
      <div className="request-table"><div className="thead" style={{ gridTemplateColumns: '.9fr 1.5fr 1fr .8fr .9fr 30px' }}><span>Request ID</span><span>Requested service</span><span>AI recommendation</span><span>Confidence</span><span>Status</span><span></span></div>
        {summary.requests.map(request => <div className="trow" style={{ gridTemplateColumns: '.9fr 1.5fr 1fr .8fr .9fr 30px', cursor: 'pointer' }} role="link" tabIndex={0} key={request.id} onClick={() => navigate(`/authorizations/${request.id}`)} onKeyDown={e => e.key === 'Enter' && navigate(`/authorizations/${request.id}`)}>
          <strong>{request.id}</strong><span>{request.service}</span><span>{request.prediction || '—'}</span><span>{request.confidence || '—'}</span><Badge type={request.tone}>{request.status}</Badge><ChevronRight size={17}/>
        </div>)}
      </div>
    </Card>
  </div></AppLayout>;
}

export function ReadonlyAuthorizationPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const { status: listStatus, error: listError } = useLiveRequests();
  const baseRequest = listStatus === 'done' ? authorizationService.getReadonlyAuthorization(user.id, id) : null;
  const needsEvaluation = Boolean(baseRequest) && !baseRequest.resultDetail;
  const { evaluation, status: triageStatus } = useTriageDetail(needsEvaluation ? id : null);

  if (listStatus !== 'done') return <AppLayout><div className="page simple"><DataState status={listStatus} error={listError}/></div></AppLayout>;
  if (!baseRequest) return <Navigate to="/dashboard" replace/>;

  const request = needsEvaluation && triageStatus === 'done' ? authorizationService.toReadonlyWithEvaluation(baseRequest, evaluation) : baseRequest;

  return <AppLayout><div className="page simple"><p className="eyebrow">AUTHORIZATION DETAIL</p><h1>{request.id}</h1><p className="lead">View-only details for your authorization request. A qualified reviewer retains final authority.</p><Card><div className="section-title"><div><p className="eyebrow">REQUEST STATUS</p><h3>{request.service}</h3></div><Badge type={request.tone}>{request.status}</Badge></div><div><div className="policy-meta"><span><b>Patient</b>{request.patient}</span></div><div className="policy-meta"><span><b>Service</b>{request.service}</span></div><div className="policy-meta"><span><b>Decision</b>{request.decision}</span></div><div className="policy-meta"><span><b>Submitted</b>{request.date}</span></div><div className="policy-meta"><span><b>Last updated</b>{request.lastUpdated}</span></div></div><div className="evidence-quote"><span><ShieldCheck size={15}/></span><div><strong>Why this result</strong><p>{request.decisionExplanation}</p>{request.missingInformation && <small>Missing information: {request.missingInformation}</small>}</div></div></Card>
    {request.resultDetail ? <AuthorizationDetail request={request}/> : needsEvaluation && triageStatus === 'loading' ? <Card><DataState status="loading"/></Card> : null}
  </div></AppLayout>;
}

function ReadonlyCategoryPage({ category, title, children }) {
  const { user } = useAuth();
  const { status: listStatus, error: listError } = useLiveRequests();
  const baseRecord = listStatus === 'done' ? authorizationService.getReadonlyRecord(user.id) : null;
  // getReadonlyRecord() never includes resultDetail on its own (same
  // cheap-list-vs-detail split everywhere else) — without this fetch, the
  // Decision page could never show anything beyond the placeholder
  // "A decision explanation will appear once the AI evaluation completes."
  // even for a request that's long since been decided. Same pattern
  // ReadonlyAuthorizationPage/ResultPage.jsx already use.
  const needsEvaluation = Boolean(baseRecord) && !baseRecord.resultDetail;
  const { evaluation, status: triageStatus } = useTriageDetail(needsEvaluation ? baseRecord.id : null);
  const record = needsEvaluation && triageStatus === 'done' ? authorizationService.toReadonlyWithEvaluation(baseRecord, evaluation) : baseRecord;
  const { documentsByAuthorization } = useDocumentsForAuthorizations(record ? [record.id] : []);

  const heading = <div className="page-heading role-hero-heading"><div><p className="role-hero-eyebrow">MEMBER PORTAL</p><h1>{title}</h1><p className="role-hero-sub">Read-only view of your prior authorization details.</p></div><Suspense fallback={<div className="hero-model"/>}><HeroModel/></Suspense></div>;

  if (listStatus !== 'done') return <AppLayout><div className="page dashboard"><DataState status={listStatus} error={listError}/></div></AppLayout>;
  if (!record) return <AppLayout><div className="page dashboard">{heading}<Card className="empty"><ShieldCheck size={27}/><h3>No authorization requests yet</h3><p>This information will appear once a request has been filed for you.</p></Card></div></AppLayout>;

  const recordWithDocuments = { ...record, documents: mapDocumentsToRows(documentsByAuthorization[record.id]) };
  return <AppLayout><div className="page dashboard">{heading}<Card className="pipeline readonly-details"><div className="section-title"><div><p className="eyebrow">{category}</p><h3>{user.name}</h3></div></div>{children(recordWithDocuments, user)}</Card></div></AppLayout>;
}

export function ReadonlyProfilePage() { return <ReadonlyCategoryPage category="PROFILE" title="Profile">{(record, user) => <div><div className="policy-meta"><span><b>Name</b>{user.name}</span></div><div className="policy-meta"><span><b>Email</b>{user.email}</span></div><div className="policy-meta"><span><b>Patient ID</b>{record?.patientId}</span></div><div className="policy-meta"><span><b>Member ID</b>{record?.memberId}</span></div><div className="policy-meta"><span><b>Age / Sex</b>{record?.age} / {record?.sex}</span></div><div className="policy-meta"><span><b>Date of birth</b>{record?.dateOfBirth}</span></div><div className="policy-meta"><span><b>Insurance plan</b>{record?.planName}</span></div><div className="policy-meta"><span><b>Coverage status</b>{record?.coverageStatus}</span></div></div>}</ReadonlyCategoryPage>; }
export function ReadonlyPolicyCategoryPage() { return <ReadonlyCategoryPage category="MY POLICY" title="My policy">{record => <div><div className="policy-meta"><span><b>Policy name</b>{record?.policyName}</span></div><div className="policy-meta"><span><b>Policy ID</b>{record?.policyId}</span></div><div className="policy-meta"><span><b>Policy type</b>{record?.policyType}</span></div><div className="policy-meta"><span><b>Effective date</b>{record?.policyEffective}</span></div><div className="policy-meta"><span><b>Coverage status</b>{record?.coverageStatus}</span></div></div>}</ReadonlyCategoryPage>; }
// Bypasses ReadonlyCategoryPage's wrapping Card, same reasoning as
// ReadonlyDecisionPage below: DiagnosisSpotlight renders its own full
// Card + section-title (icon badge, eyebrow, "View only" tag), so handing
// it to ReadonlyCategoryPage as a child would nest a card inside a card.
// Duplicates ReadonlyCategoryPage's own record-fetch logic for that reason
// — same tradeoff ReadonlyDecisionPage already made for AuthorizationDetail.
export function ReadonlyDiagnosisPage() {
  const { user } = useAuth();
  const { status: listStatus, error: listError } = useLiveRequests();
  const baseRecord = listStatus === 'done' ? authorizationService.getReadonlyRecord(user.id) : null;
  const needsEvaluation = Boolean(baseRecord) && !baseRecord.resultDetail;
  const { evaluation, status: triageStatus } = useTriageDetail(needsEvaluation ? baseRecord.id : null);
  const record = needsEvaluation && triageStatus === 'done' ? authorizationService.toReadonlyWithEvaluation(baseRecord, evaluation) : baseRecord;

  if (listStatus !== 'done') return <AppLayout><div className="page dashboard"><DataState status={listStatus} error={listError}/></div></AppLayout>;
  if (!record) return <AppLayout><div className="page dashboard"><div className="page-heading"><div><h1>Diagnosis</h1></div></div><Card className="empty"><ShieldCheck size={27}/><h3>No authorization requests yet</h3><p>This information will appear once a request has been filed for you.</p></Card></div></AppLayout>;

  const criteria = record.resultDetail?.criteria || [];

  return <AppLayout><div className="page dashboard">
    <div className="page-heading"><div><h1>Diagnosis</h1></div></div>
    <DiagnosisSpotlight diagnosis={record.diagnosis} icdCode={record.icd10} secondaryDiagnoses={record.secondaryDiagnoses} clinicalHistory={record.clinicalHistory} urgency={record.urgency} status={record.status}/>

    {/* Bridges diagnosis -> the specific request it's tied to. Real fields
        already on `record` (toReadonlyRequest in authorizationService.js) —
        nothing invented. Deliberately a short headline + link out to
        /decision rather than the full report: AuthorizationDetail already
        owns that, this page's job is orientation, not duplication. */}
    <Card style={{ marginTop: 15 }}>
      <div className="section-title"><div><p className="eyebrow">RELATED AUTHORIZATION</p><h3>{record.service}</h3></div><Badge type={record.tone}>{record.status}</Badge></div>
      <div className="policy-meta">
        <span><b>Request ID</b>{record.id}</span>
        <span><b>Procedure code</b>{record.procedureCode || 'Not provided'}</span>
        <span><b>Care setting</b>{record.careSetting || 'Not provided'}</span>
        <span><b>Submitted</b>{record.date}</span>
      </div>
      <div className="evidence-quote"><span><ShieldCheck size={15}/></span><div><strong>Decision: {record.decision}</strong><p>{record.decisionExplanation}</p></div></div>
      <a className="bottom-link" href="/decision">View full decision <ChevronRight size={14}/></a>
    </Card>

    {/* Real clinical criteria evaluated against THIS diagnosis (same
        `criteria` AuthorizationDetail renders, built from the actual
        clinicalCriteriaEval.criteriaResults — see requestMapper.js) —
        omitted entirely rather than showing a placeholder when no
        evaluation exists yet. */}
    {criteria.length > 0 && <Card style={{ marginTop: 15 }}>
      <div className="section-title"><div><p className="eyebrow">CLINICAL CRITERIA</p><h3>Evaluated for this diagnosis</h3></div></div>
      {criteria.map(([label, result, tone]) => <div className="criteria" key={label}><span className={`dot ${tone}`}></span><span>{label}</span><Badge type={tone}>{result}</Badge></div>)}
    </Card>}
  </div></AppLayout>;
}
export function ReadonlyRequestPage() { return <ReadonlyCategoryPage category="MY REQUEST" title="My request">{record => <div><div className="policy-meta"><span><b>Procedure</b>{record?.service}</span></div><div className="policy-meta"><span><b>Procedure code</b>{record?.procedureCode}</span></div><div className="policy-meta"><span><b>Urgency</b>{record?.urgency}</span></div><div className="policy-meta"><span><b>Care setting</b>{record?.careSetting}</span></div><div className="policy-meta"><span><b>Status</b>{record?.status}</span></div><div className="policy-meta"><span><b>Submitted</b>{record?.date}</span></div><div className="policy-meta"><span><b>Last updated</b>{record?.lastUpdated}</span></div></div>}</ReadonlyCategoryPage>; }
// Deliberately bypasses ReadonlyCategoryPage's wrapping Card — Card is a
// plain "section.card" (components/ui/index.jsx), and AuthorizationDetail
// renders its own Cards internally, so nesting them would double-wrap
// borders/shadow. This mirrors ReviewerAuthorization.jsx's own layout for
// the same full-report component, just view-only (no export button, no
// reviewer decision form).
export function ReadonlyDecisionPage() {
  const { user } = useAuth();
  const { status: listStatus, error: listError } = useLiveRequests();
  const baseRecord = listStatus === 'done' ? authorizationService.getReadonlyRecord(user.id) : null;
  const needsEvaluation = Boolean(baseRecord) && !baseRecord.resultDetail;
  const { evaluation, status: triageStatus } = useTriageDetail(needsEvaluation ? baseRecord.id : null);
  const record = needsEvaluation && triageStatus === 'done' ? authorizationService.toReadonlyWithEvaluation(baseRecord, evaluation) : baseRecord;

  if (listStatus !== 'done') return <AppLayout><div className="page dashboard"><DataState status={listStatus} error={listError}/></div></AppLayout>;
  if (!record) return <AppLayout><div className="page dashboard"><div className="page-heading"><div><h1>Decision</h1></div></div><Card className="empty"><ShieldCheck size={27}/><h3>No authorization requests yet</h3><p>This information will appear once a request has been filed for you.</p></Card></div></AppLayout>;

  return <AppLayout><div className="page dashboard readonly-details">
    <div className="page-heading"><div><p className="eyebrow">DECISION</p><h1>{user.name}</h1></div></div>
    {record.resultDetail ? <AuthorizationDetail request={record}/> : needsEvaluation && triageStatus === 'loading'
      ? <Card><DataState status="loading"/></Card>
      : <Card><p className="body-copy">AI triage detail is not available for this request yet.</p></Card>}
  </div></AppLayout>;
}
export function ReadonlyDocumentsPage() { return <ReadonlyCategoryPage category="DOCUMENTS" title="Documents">{record => <div>{record?.documents.length ? record.documents.map(document => <DocumentRow key={document.id} document={document}/>) : <p className="body-copy">No documents on file yet.</p>}</div>}</ReadonlyCategoryPage>; }
export function ReadonlyTimelinePage() { return <ReadonlyCategoryPage category="TIMELINE" title="Timeline">{record => <div>{record?.timeline.map((event, index) => <div className="policy-meta" key={event}><span><b>{event}</b>{index === 0 ? record.date : index === 1 ? 'In progress' : record.lastUpdated}</span></div>)}</div>}</ReadonlyCategoryPage>; }
