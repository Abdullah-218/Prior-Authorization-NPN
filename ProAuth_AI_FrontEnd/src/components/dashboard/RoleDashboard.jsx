import { lazy, Suspense, useState } from 'react';
import { AlertTriangle, ChevronRight, Clock3, FileText, Plus, ShieldCheck, UploadCloud, UserCheck, Zap } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import AppLayout from '../layout/AppLayout';
import { Badge, Card, DataState, Icon, Pager } from '../ui';
import { useAuth } from '../../hooks/useAuth';
import { useLiveRequests } from '../../hooks/useLiveRequests';
import { usePriorityQueue } from '../../hooks/usePriorityQueue';
import { requests } from '../../data/requests';
import { ReadonlyDashboard as ReadonlyDashboardContent } from '../../pages/ReadonlyViews';
import { dashboardService } from '../../services/dashboardService';
import PolicyIntelligenceHub from '../policy/PolicyIntelligenceHub';
import '../../features/nurse/nurse-review.css';

const HeroModel = lazy(() => import('./HeroModel'));
const TIER_TONE = { HIGH: 'red', MEDIUM: 'amber', LOW: 'blue' };
// Fixed floor added on top of the real, live tier tally on the nurse
// overview tiles — per explicit request, so the tiles never read as
// empty/awkward (e.g. "Moderate risk: 0") during a live demo, while the
// real count still moves on top of it exactly as it does today. Does not
// touch the per-row Priority badges in the table below, which stay 100%
// real — only these 3 aggregate tiles.
const TIER_BASE_COUNT = { HIGH: 15, MEDIUM: 10, LOW: 20 };

const DOCTOR_PATIENTS_PAGE_SIZE = 12;

function DoctorDashboard({ user }) {
  const navigate = useNavigate();
  const { status, error } = useLiveRequests();
  const [patientPage, setPatientPage] = useState(1);
  if (status !== 'done') return <AppLayout><div className="page dashboard"><DataState status={status} error={error} /></div></AppLayout>;
  const dashboard = dashboardService.getDoctorDashboard(user.id);
  const stats = [
    { label: 'Total requests', value: dashboard.requests.length, note: 'All submitted requests', tone: 'blue', icon: FileText, path: '/doctor/requests' },
    { label: 'Need more information', value: dashboard.moreInformationRequests.length, note: 'Awaiting additional evidence', tone: 'amber', icon: UploadCloud, path: '/doctor/requests/need-information' },
    { label: 'Automated approval', value: dashboard.automatedApprovals.length, note: 'Approved by AI, no human touch', tone: 'green', icon: Zap, path: '/doctor/requests/automated' },
    { label: 'Manually approved', value: dashboard.manualApprovals.length, note: 'By a nurse or insurance admin', tone: 'blue', icon: UserCheck, path: '/doctor/requests/manual' }
  ];
  // Client-side pagination — dashboard.patients is already fully in memory
  // (derived from the shared requests[] array), so this is a slice, not a
  // new fetch. Same pattern already used on NursePatients.jsx/
  // ReviewerPatients.jsx.
  const patientTotalPages = Math.max(1, Math.ceil(dashboard.patients.length / DOCTOR_PATIENTS_PAGE_SIZE));
  const patientCurrentPage = Math.min(patientPage, patientTotalPages);
  const visiblePatients = dashboard.patients.slice((patientCurrentPage - 1) * DOCTOR_PATIENTS_PAGE_SIZE, patientCurrentPage * DOCTOR_PATIENTS_PAGE_SIZE);
  return <AppLayout><div className="page dashboard"><div className="page-heading role-hero-heading"><div><p className="role-hero-eyebrow">DOCTOR WORKSPACE</p><h1>Welcome, {user.name}</h1><p className="role-hero-sub">Track your prior authorization requests and see AI-driven outcomes in real time.</p><a className="button primary hero-cta" href="/new-authorization"><Plus size={17}/>New authorization</a></div><Suspense fallback={<div className="hero-model"/>}><HeroModel/></Suspense></div><div className="stat-grid doctor-stat-grid">{stats.map(stat => { const activate = () => navigate(stat.path); return <div className="card stat" role="button" tabIndex={0} key={stat.path} onClick={activate} onKeyDown={event => event.key === 'Enter' && activate()}><div><p>{stat.label}</p><h2>{stat.value}</h2><small className={stat.tone}>{stat.note}</small></div><Icon tone={stat.tone}><stat.icon size={18}/></Icon></div>; })}</div><Card className="attention"><div className="section-title"><div><p className="eyebrow">MY PATIENTS</p><h3>Patient authorization status</h3></div><Badge type="blue">{dashboard.patients.length} patients</Badge></div><div className="request-table"><div className="thead" style={{gridTemplateColumns:'1fr 1.4fr 1.4fr .8fr 1.1fr 30px'}}><span>Patient ID</span><span>Patient Name</span><span>Diagnosis</span><span>Active Requests</span><span>Latest Status</span><span>Action</span></div>{visiblePatients.map(patient => { const activate = () => navigate(`/doctor/patients/${patient.patientId}`); return <div className="trow" style={{gridTemplateColumns:'1fr 1.4fr 1.4fr .8fr 1.1fr 30px', cursor:'pointer'}} role="link" tabIndex="0" onClick={activate} onKeyDown={event => event.key === 'Enter' && activate()} key={patient.patientId}><strong>{patient.patientId}</strong><button className="text-button" type="button" onClick={event => { event.stopPropagation(); activate(); }}>{patient.patient}</button><span>{patient.diagnosis}</span><span>{patient.activeRequests}</span><Badge type={patient.latestStatus === 'Approved' ? 'green' : patient.latestStatus === 'Additional Information Required' ? 'amber' : patient.latestStatus === 'Denied' ? 'red' : 'blue'}>{patient.latestStatus}</Badge><button className="open" type="button" onClick={event => { event.stopPropagation(); activate(); }}><ChevronRight size={17}/></button></div>; })}</div></Card><Pager page={patientCurrentPage} totalPages={patientTotalPages} total={dashboard.patients.length} onChange={setPatientPage}/></div></AppLayout>;
}

function ReviewerDashboard({ user }) {
  const navigate = useNavigate();
  const { status, error } = useLiveRequests();
  if (status !== 'done') return <AppLayout><div className="page dashboard"><DataState status={status} error={error} /></div></AppLayout>;
  const dashboard = dashboardService.getInsuranceDashboard();
  const stats = [
    { label: 'Total requests', value: dashboard.requests.length, note: 'Across all patients', tone: 'blue', icon: FileText, path: '/insurance/requests' },
    { label: 'Automated Approved', value: dashboard.automatedApprovals.length, note: 'Approved without manual review', tone: 'green', icon: Zap, path: '/insurance/requests/automated' },
    { label: 'Manually approved', value: dashboard.manualApprovals.length, note: 'By a nurse or admin reviewer', tone: 'blue', icon: UserCheck, path: '/insurance/requests/manual' },
    { label: 'Pending', value: dashboard.pendingCases.length, note: 'Awaiting your decision', tone: 'amber', icon: Clock3, path: '/queue' }
  ];
  const viewPatient = request => navigate(`/patients/${request.patientId || request.id}`);
  // Sorted explicitly by submittedAtRaw rather than trusting requests[]'s
  // own order — that array is populated two different ways (a bulk load
  // that's backend-sorted newest-first, and upsertRequest() appending a
  // single updated row to the END), so "most recent" can't be assumed
  // from position alone. Same fix already applied to patientService.js
  // this session for the identical reason.
  const recentDecisions = [...requests]
    .filter(request => request.status === 'Approved' || request.status === 'Denied')
    .sort((a, b) => new Date(b.submittedAtRaw || 0) - new Date(a.submittedAtRaw || 0))
    .slice(0, 5);
  return <AppLayout><div className="page dashboard"><div className="page-heading role-hero-heading"><div><p className="role-hero-eyebrow">INSURANCE AUTHORIZATION CENTER</p><h1>Welcome, Insurance Admin</h1><p className="role-hero-sub">Oversee claims, policy coverage, and authorization outcomes across all patients.</p><a className="button primary hero-cta" href="/queue">Open queue <ChevronRight size={16}/></a></div><Suspense fallback={<div className="hero-model"/>}><HeroModel/></Suspense></div><div className="stat-grid reviewer-stat-grid">{stats.map(stat => { const activate = () => navigate(stat.path); return <div className="card stat" role="button" tabIndex={0} key={stat.path} onClick={activate} onKeyDown={event => event.key === 'Enter' && activate()}><div><p>{stat.label}</p><h2>{stat.value}</h2><small className={stat.tone}>{stat.note}</small></div><Icon tone={stat.tone}><stat.icon size={18}/></Icon></div>; })}</div><Card className="attention"><div className="section-title"><div><p className="eyebrow">POLICY INTELLIGENCE HUB</p><h3>Policy Intelligence Hub</h3><p className="pih-heading-sub">How ProAuth IQ evaluates an authorization against the applicable policy</p></div><Badge type="blue">View only</Badge></div><PolicyIntelligenceHub/></Card><Card className="attention reviewer-activity-card"><div className="section-title"><div><p className="eyebrow">RECENT DECISIONS</p><h3>Authorization activity</h3></div><Badge type="blue">Last 5</Badge></div><div className="decision-list">{recentDecisions.map(request => <button className="decision-row" type="button" key={request.id} onClick={() => viewPatient(request)}>
    <div className={`mini-avatar ${request.tone}`}>{request.initials}</div>
    <div className="decision-row-main"><strong>{request.id} · {request.patient}</strong><small>{request.service}{request.diagnosis && request.diagnosis !== 'Not specified' ? ` · ${request.diagnosis}` : ''}</small></div>
    <Badge type={request.approvalType === 'automated' ? 'green' : request.approvalType === 'manual' ? 'blue' : 'neutral'}>{request.approvalType === 'automated' ? 'Automated' : request.approvalType === 'manual' ? 'Manual' : 'Legacy'}</Badge>
    <Badge type={request.tone}>{request.status}</Badge>
    <small className="decision-row-date">{request.date}</small>
    <ChevronRight size={17}/>
  </button>)}{recentDecisions.length === 0 && <p className="body-copy">No decisions recorded yet.</p>}</div></Card></div></AppLayout>;
}

function NurseDashboard({ user }) {
  const navigate = useNavigate();
  const { status, error } = useLiveRequests();
  const { priorityByAuthorization, status: priorityStatus } = usePriorityQueue();
  if (status !== 'done') return <AppLayout><div className="page dashboard"><DataState status={status} error={error} /></div></AppLayout>;
  const reviewRequests = requests.filter(request => request.prediction === 'Nurse review' || request.status === 'Needs Review');
  const evidenceNeededCount = requests.filter(request => request.status === 'Additional Information Required').length;
  const viewPatient = request => navigate(`/patients/${request.patientId || request.id}`);

  const tierCounts = { HIGH: 0, MEDIUM: 0, LOW: 0 };
  if (priorityStatus === 'done') {
    reviewRequests.forEach(request => {
      const tier = priorityByAuthorization[request.id]?.priorityTier;
      if (tier && tier in tierCounts) tierCounts[tier] += 1;
    });
  }

  // Dashboard overview is a snapshot, not the full queue — cap it to the
  // 15 most recently submitted cases (open review queue for everything
  // else) so it doesn't grow into a long, unbounded scroll on this page.
  // tierCounts above is still computed from the FULL reviewRequests set,
  // not this slice, so the stat tiles keep reflecting the whole queue.
  const recentReviewRequests = [...reviewRequests]
    .sort((a, b) => new Date(b.submittedAtRaw || 0) - new Date(a.submittedAtRaw || 0))
    .slice(0, 15);

  const stats = [
    { label: 'High risk', value: TIER_BASE_COUNT.HIGH + tierCounts.HIGH, note: 'Review first', tone: 'red', icon: AlertTriangle, path: '/nurse/review/high' },
    { label: 'Moderate risk', value: TIER_BASE_COUNT.MEDIUM + tierCounts.MEDIUM, note: 'Review soon', tone: 'amber', icon: Clock3, path: '/nurse/review/moderate' },
    { label: 'Low risk', value: TIER_BASE_COUNT.LOW + tierCounts.LOW, note: 'Routine', tone: 'blue', icon: ShieldCheck, path: '/nurse/review/low' },
    { label: 'Evidence requests', value: evidenceNeededCount, note: 'Awaiting information', tone: 'blue', icon: FileText, path: '/nurse/review' },
  ];
  return <AppLayout><div className="page dashboard"><div className="page-heading role-hero-heading"><div><p className="role-hero-eyebrow">NURSE REVIEW STATION</p><h1>Welcome to the Nurse Reviewer Panel</h1><p className="role-hero-sub">Review flagged authorizations and finalize clinical decisions.</p><a className="button primary hero-cta" href="/nurse/review">Open review queue <ChevronRight size={16}/></a></div><Suspense fallback={<div className="hero-model"/>}><HeroModel/></Suspense></div><div className="stat-grid nurse-stat-grid">{stats.map(stat => { const activate = () => navigate(stat.path); return <div className="card stat" role="button" tabIndex={0} key={stat.path} onClick={activate} onKeyDown={event => event.key === 'Enter' && activate()}><div><p>{stat.label}</p><h2>{stat.value}</h2><small className={stat.tone}>{stat.note}</small></div><Icon tone={stat.tone}><stat.icon size={18}/></Icon></div>; })}</div><Card className="attention"><div className="section-title"><div><p className="eyebrow">CLINICAL REVIEW QUEUE</p><h3>Requests to review</h3></div><div style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Badge type="blue">Human review</Badge><Badge type="neutral">Recent 15</Badge></div></div><div className="request-table clinical-review-table"><div className="thead"><span>Priority</span><span>Request ID</span><span>Patient</span><span>Diagnosis</span><span>Requested Service</span><span>Policy</span><span>ML Prediction</span><span className="confidence-column">Confidence</span><span>Status</span><span>Submitted</span></div>{recentReviewRequests.map(request => { const priority = priorityByAuthorization[request.id]; return <div className="trow" style={{ cursor: 'pointer' }} role="link" tabIndex={0} key={request.id} onClick={() => viewPatient(request)} onKeyDown={event => event.key === 'Enter' && viewPatient(request)}><span className="priority-column" title={priority?.reasonCodes?.join(' · ') || ''}>{priority?.priorityTier ? <Badge type={TIER_TONE[priority.priorityTier] || 'blue'}>{priority.priorityTier}</Badge> : <Badge type="blue">—</Badge>}</span><strong>{request.id}</strong><span className="truncate-cell" title={request.patient}>{request.patient}</span><span className="truncate-cell" title={request.diagnosis}>{request.diagnosis || '—'}</span><span className="truncate-cell" title={request.service}>{request.service}</span><span className="truncate-cell" title={request.policy || request.policyName}>{request.policy || request.policyName || '—'}</span><span><Badge type={request.tone}>{request.prediction || '—'}</Badge></span><span className="confidence-column">{request.confidence || '—'}</span><span><Badge type={request.tone}>{request.status}</Badge></span><small>{request.date}</small></div>; })}</div>{reviewRequests.length === 0 && <div className="empty"><FileText size={27}/><h3>No requests in review</h3><p>Clinical review items will appear here.</p></div>}{reviewRequests.length > 15 && <a className="bottom-link" href="/nurse/review">View all {reviewRequests.length} in review queue <ChevronRight size={14}/></a>}</Card></div></AppLayout>;
}

function ReadonlyDashboard({ user }) { return <ReadonlyDashboardContent user={user}/>; }

export default function RoleDashboard() {
  const { user } = useAuth();
  if (user.role === 'doctor') return <DoctorDashboard user={user}/>;
  if (user.role === 'nurse') return <NurseDashboard user={user}/>;
  if (user.role === 'user' || user.role === 'readonly') return <ReadonlyDashboard user={user}/>;
  return <ReviewerDashboard user={user}/>;
}
