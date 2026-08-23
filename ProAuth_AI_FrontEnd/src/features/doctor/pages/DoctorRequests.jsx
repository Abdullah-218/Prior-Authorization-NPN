import { useEffect, useState } from 'react';
import { ChevronRight, UploadCloud } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import AppLayout from '../../../components/layout/AppLayout';
import { Badge, Card, DataState, Pager } from '../../../components/ui';
import { useAuth } from '../../../hooks/useAuth';
import { useLiveRequests } from '../../../hooks/useLiveRequests';
import { dashboardService } from '../../../services/dashboardService';

const filters = {
  '/doctor/requests': 'ALL',
  '/doctor/requests/approved': 'APPROVED',
  '/doctor/requests/automated': 'AUTOMATED',
  '/doctor/requests/manual': 'MANUAL',
  '/doctor/requests/need-information': 'NEED_MORE_INFORMATION'
};

const pageDetails = {
  ALL: { title: 'Total requests' },
  APPROVED: { title: 'Approved requests' },
  AUTOMATED: { title: 'Automated approval' },
  MANUAL: { title: 'Manually approved' },
  NEED_MORE_INFORMATION: { title: 'Need more information' }
};

// AUTOMATED/MANUAL/APPROVED share the same table shape (all three are
// approved-request subsets) — one flag instead of three separate blocks.
const APPROVED_LIKE = ['APPROVED', 'AUTOMATED', 'MANUAL'];

const PAGE_SIZE = 12;

export default function DoctorRequests() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const filter = filters[pathname] || 'ALL';
  const { status, error } = useLiveRequests();
  const [page, setPage] = useState(1);
  const detail = pageDetails[filter];

  // Switching tabs (Total/Approved/Need info) resets back to page 1 —
  // page 3 of a different filter's results isn't meaningful.
  useEffect(() => { setPage(1); }, [filter]);

  if (status !== 'done') return <AppLayout><div className="page queue"><div className="page-heading"><div><h1>{detail.title}</h1></div></div><DataState status={status} error={error} /></div></AppLayout>;
  const dashboard = dashboardService.getDoctorDashboard(user.id);
  const visibleRequests = filter === 'APPROVED' ? dashboard.approvedRequests
    : filter === 'AUTOMATED' ? dashboard.automatedApprovals
    : filter === 'MANUAL' ? dashboard.manualApprovals
    : filter === 'NEED_MORE_INFORMATION' ? dashboard.moreInformationRequests
    : dashboard.requests;
  // Client-side pagination — visibleRequests is already fully in memory
  // (derived from the shared requests[] array), so this is a slice, not a
  // new fetch. Same pattern already used on NursePatients.jsx/
  // ReviewerPatients.jsx.
  const totalPages = Math.max(1, Math.ceil(visibleRequests.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageRequests = visibleRequests.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const viewPatient = request => navigate(`/doctor/patients/${request.patientId || request.id}`);

  return <AppLayout><div className="page queue"><div className="page-heading"><div><h1>{detail.title}</h1></div></div><Card><div className="request-table">
    {filter === 'ALL' && <><div className="thead" style={{gridTemplateColumns:'1fr 1.3fr 1.4fr 1.4fr 1fr 1.1fr 30px'}}><span>Request ID</span><span>Patient</span><span>Diagnosis</span><span>Requested service</span><span>Status</span><span>Submitted date</span><span>Action</span></div>{pageRequests.map(request => <div className="trow" style={{gridTemplateColumns:'1fr 1.3fr 1.4fr 1.4fr 1fr 1.1fr 30px', cursor:'pointer'}} role="link" tabIndex={0} key={request.id} onClick={() => viewPatient(request)} onKeyDown={event => event.key === 'Enter' && viewPatient(request)}><strong>{request.id}</strong><span>{request.patient}</span><span>{request.diagnosis}</span><span>{request.service}</span><Badge type={request.tone}>{request.status}</Badge><small>{request.date}</small><button className="open" type="button" onClick={event => { event.stopPropagation(); viewPatient(request); }}><ChevronRight size={17}/></button></div>)}</>}
    {APPROVED_LIKE.includes(filter) && <><div className="thead" style={{gridTemplateColumns:'1fr 1.2fr 1.4fr 1.2fr 1.2fr .8fr 1fr 1.1fr 30px'}}><span>Request ID</span><span>Patient</span><span>Requested service</span><span>Policy</span><span>AI recommendation</span><span>Confidence</span><span>Status</span><span>Date</span><span>Action</span></div>{pageRequests.map(request => <div className="trow" style={{gridTemplateColumns:'1fr 1.2fr 1.4fr 1.2fr 1.2fr .8fr 1fr 1.1fr 30px', cursor:'pointer'}} role="link" tabIndex={0} key={request.id} onClick={() => viewPatient(request)} onKeyDown={event => event.key === 'Enter' && viewPatient(request)}><strong>{request.id}</strong><span>{request.patient}</span><span>{request.service}</span><span>{request.policyName || 'Not specified'}</span><span>{request.prediction}</span><span>{request.confidence || '—'}</span><Badge type={request.tone}>{request.status}</Badge><small>{request.date}</small><button className="open" type="button" onClick={event => { event.stopPropagation(); viewPatient(request); }}><ChevronRight size={17}/></button></div>)}</>}
    {filter === 'NEED_MORE_INFORMATION' && <><div className="thead" style={{gridTemplateColumns:'1fr 1.2fr 1.4fr 1.4fr 1.4fr 1fr 1.9fr'}}><span>Request ID</span><span>Patient</span><span>Requested service</span><span>Missing information</span><span>Missing documents</span><span>Date requested</span><span>Action</span></div>{pageRequests.map(request => <div className="trow" style={{gridTemplateColumns:'1fr 1.2fr 1.4fr 1.4fr 1.4fr 1fr 1.9fr', cursor:'pointer'}} role="link" tabIndex={0} key={request.id} onClick={() => viewPatient(request)} onKeyDown={event => event.key === 'Enter' && viewPatient(request)}><strong>{request.id}</strong><span>{request.patient}</span><span>{request.service}</span><span>{request.missingInformation}</span><span>{request.requiredDocument || request.documents?.find(([, status]) => status === 'Missing')?.[0] || 'Not specified'}</span><small>{request.date}</small><span className="need-info-actions"><span className="need-info-actions-row"><button className="button compact" type="button" onClick={event => { event.stopPropagation(); viewPatient(request); }}>View</button><button className="button compact primary" type="button" onClick={event => { event.stopPropagation(); navigate(`/doctor/resubmit/${request.id}`); }}><UploadCloud size={13}/>Upload info</button></span><button className="button compact full" type="button" onClick={event => { event.stopPropagation(); navigate(`/doctor/resubmit/${request.id}`); }}>Resubmit</button></span></div>)}</>}
  </div></Card><Pager page={currentPage} totalPages={totalPages} total={visibleRequests.length} onChange={setPage}/></div></AppLayout>;
}
