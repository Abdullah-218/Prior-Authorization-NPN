import { useEffect, useState } from 'react';
import { CircleHelp, FileText } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import AppLayout from '../../../components/layout/AppLayout';
import { Badge, Card, DataState, Pager } from '../../../components/ui';
import { dashboardService } from '../../../services/dashboardService';
import { useLiveRequests } from '../../../hooks/useLiveRequests';
import { usePriorityQueue } from '../../../hooks/usePriorityQueue';
import '../nurse-review.css';

const TIER_TONE = { HIGH: 'red', MEDIUM: 'amber', LOW: 'blue' };
const PAGE_SIZE = 12;

const filters = {
  '/nurse/review': 'ALL',
  '/nurse/review/high': 'HIGH',
  '/nurse/review/moderate': 'MEDIUM',
  '/nurse/review/low': 'LOW',
};

const TIER_TABS = [
  { path: '/nurse/review', label: 'All priorities' },
  { path: '/nurse/review/high', label: 'High' },
  { path: '/nurse/review/moderate', label: 'Moderate' },
  { path: '/nurse/review/low', label: 'Low' },
];

const pageDetails = {
  ALL: { title: 'Clinical review queue', eyebrow: 'PENDING CLINICAL REVIEW' },
  HIGH: { title: 'High risk cases', eyebrow: 'HIGH PRIORITY' },
  MEDIUM: { title: 'Moderate risk cases', eyebrow: 'MODERATE PRIORITY' },
  LOW: { title: 'Low risk cases', eyebrow: 'LOW PRIORITY' },
};

export default function NurseReview() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { status: listStatus, error: listError } = useLiveRequests();
  const { priorityByAuthorization, status: priorityStatus } = usePriorityQueue();
  const [page, setPage] = useState(1);
  const filter = filters[pathname] || 'ALL';
  const detail = pageDetails[filter];
  const requests = dashboardService.getNurseDashboard().requests;
  const viewPatient = request => navigate(`/patients/${request.patientId || request.id}`);

  // Switching tabs (All/High/Moderate/Low) resets back to page 1 — page 3
  // of a different filter's results isn't meaningful.
  useEffect(() => { setPage(1); }, [filter]);

  if (listStatus !== 'done') return <AppLayout><div className="page queue"><DataState status={listStatus} error={listError}/></div></AppLayout>;

  // Priority ranking is an enhancement, not a blocker for the ALL view —
  // it still renders in normal order if the priority service is slow or
  // down. A tier-filtered view (High/Moderate/Low) genuinely can't show
  // anything meaningful without priority data, so those show a loading
  // state instead of a false "no cases" empty state while it's in flight.
  const sortedRequests = priorityStatus === 'done'
    ? [...requests].sort((a, b) => {
        const rankA = priorityByAuthorization[a.id]?.queueRank ?? Infinity;
        const rankB = priorityByAuthorization[b.id]?.queueRank ?? Infinity;
        return rankA - rankB;
      })
    : requests;
  const visibleRequests = filter === 'ALL'
    ? sortedRequests
    : sortedRequests.filter(request => priorityByAuthorization[request.id]?.priorityTier === filter);
  const stillWaitingOnPriority = filter !== 'ALL' && priorityStatus !== 'done';
  // Client-side pagination — this list is already fully in memory (derived
  // from the shared requests[] array plus priority ranks), so pagination
  // here is a slice, not a new fetch. Fixes this queue being fully,
  // unboundedly scrollable once there are more than a handful of cases.
  const totalPages = Math.max(1, Math.ceil(visibleRequests.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageRequests = visibleRequests.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  return <AppLayout><div className="page queue">
    <div className="page-heading"><div><p className="eyebrow">{detail.eyebrow}</p><h1>{detail.title}</h1></div><Badge type="blue">{stillWaitingOnPriority ? '…' : visibleRequests.length} request{visibleRequests.length === 1 ? '' : 's'}</Badge></div>
    <Card className="attention"><div className="section-title"><div><p className="eyebrow">REVIEW GUIDANCE</p><h3>Human-in-the-loop workflow</h3></div><CircleHelp size={18}/></div><p className="body-copy">Review patient context, submitted evidence, policy criteria, and the AI recommendation before requesting information or making a clinical recommendation. Priority reflects SLA pressure, urgency, and clinical risk — hover the badge for the specific reasons.</p></Card>
    <Card><div className="section-title"><div><p className="eyebrow">{detail.eyebrow}</p><h3>Requests needing attention</h3></div><Badge type="blue">Human review</Badge></div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', padding: '0 0 14px' }}>{TIER_TABS.map(t => <button key={t.path} className={`button compact ${pathname === t.path ? 'primary' : ''}`} type="button" onClick={() => navigate(t.path)}>{t.label}</button>)}</div>
      {stillWaitingOnPriority ? <DataState status="loading"/> : <div className="request-table clinical-review-table">
        <div className="thead"><span>Priority</span><span>Request ID</span><span>Patient</span><span>Diagnosis</span><span>Requested Service</span><span>Policy</span><span>ML Prediction</span><span className="confidence-column">Confidence</span><span>Status</span><span>Submitted</span></div>
        {pageRequests.map(request => { const priority = priorityByAuthorization[request.id]; return <div className="trow" style={{ cursor: 'pointer' }} role="link" tabIndex={0} key={request.id} onClick={() => viewPatient(request)} onKeyDown={event => event.key === 'Enter' && viewPatient(request)}><span className="priority-column" title={priority?.reasonCodes?.join(' · ') || ''}>{priority?.priorityTier ? <Badge type={TIER_TONE[priority.priorityTier] || 'blue'}>{priority.priorityTier}</Badge> : <Badge type="blue">—</Badge>}</span><strong>{request.id}</strong><span className="truncate-cell" title={request.patient}>{request.patient}</span><span className="truncate-cell" title={request.diagnosis}>{request.diagnosis || '—'}</span><span className="truncate-cell" title={request.service}>{request.service}</span><span className="truncate-cell" title={request.policy || request.policyName}>{request.policy || request.policyName || '—'}</span><span><Badge type={request.tone}>{request.prediction || '—'}</Badge></span><span className="confidence-column">{request.confidence || '—'}</span><span><Badge type={request.tone}>{request.status}</Badge></span><small>{request.date}</small></div>; })}
      </div>}
      {!stillWaitingOnPriority && visibleRequests.length === 0 && <div className="empty"><FileText size={27}/><h3>No requests in this category</h3><p>{filter === 'ALL' ? 'Clinical review items will appear here.' : 'Requests at this priority level will appear here.'}</p></div>}
    </Card>
    {!stillWaitingOnPriority && <Pager page={currentPage} totalPages={totalPages} total={visibleRequests.length} onChange={setPage}/>}
  </div></AppLayout>;
}
