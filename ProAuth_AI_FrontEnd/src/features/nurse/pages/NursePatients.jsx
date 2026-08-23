import { useState } from 'react';
import { ChevronRight, Users } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import AppLayout from '../../../components/layout/AppLayout';
import { Badge, Card, DataState, Pager } from '../../../components/ui';
import { dashboardService } from '../../../services/dashboardService';
import { patientService } from '../../../services/patientService';
import { useLiveRequests } from '../../../hooks/useLiveRequests';

const columns = '.8fr 1.3fr .45fr .5fr 1.3fr .8fr 1fr .95fr 1fr';
const PAGE_SIZE = 12;

// Patients here are DERIVED (grouped client-side from the already-loaded
// requests[] array, not a paginated API of their own) — so pagination is
// client-side slicing of an already-in-memory list, same pattern as
// ReviewerPatients.jsx. Fixes this page being fully, unboundedly
// scrollable once there are more than a handful of patients in review.
export default function NursePatients() {
  const navigate = useNavigate();
  const { status: listStatus, error: listError } = useLiveRequests();
  const [page, setPage] = useState(1);
  const { requests } = dashboardService.getNurseDashboard();
  const patients = patientService.getPatientsFromList(requests);

  if (listStatus !== 'done') return <AppLayout><div className="page simple"><DataState status={listStatus} error={listError}/></div></AppLayout>;

  const totalPages = Math.max(1, Math.ceil(patients.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const visiblePatients = patients.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  return <AppLayout><div className="page simple"><h1>Patients</h1><Card><div className="section-title"><div><p className="eyebrow">PATIENT REVIEW STATUS</p><h3>Patients needing attention</h3></div><Badge type="blue">{patients.length} patients</Badge></div><div className="request-table"><div className="thead" style={{ gridTemplateColumns: columns }}><span>Patient ID</span><span>Patient Name</span><span>Age</span><span>Sex</span><span>Primary Diagnosis</span><span>Active Requests</span><span>Latest Status</span><span>Last Updated</span><span>Action</span></div>{visiblePatients.map(patient => { const activate = () => navigate(`/patients/${patient.patientId}`); return <div className="trow" style={{ gridTemplateColumns: columns, cursor: 'pointer' }} role="link" tabIndex={0} key={patient.patientId} onClick={activate} onKeyDown={event => event.key === 'Enter' && activate()}><strong>{patient.patientId}</strong><span>{patient.patient}</span><span>{patient.age || '—'}</span><span>{patient.sex || '—'}</span><span>{patient.diagnosis}</span><span>{patient.activeRequests}</span><Badge type={patient.latestStatus === 'Additional Information Required' ? 'amber' : 'blue'}>{patient.latestStatus}</Badge><span>{patient.lastUpdated}</span><button className="text-button" type="button" onClick={event => { event.stopPropagation(); activate(); }}>View Patient <ChevronRight size={14}/></button></div>; })}</div>{patients.length === 0 && <div className="empty"><Users size={27}/><h3>No patients require review</h3><p>Patients connected to clinical review requests will appear here.</p></div>}</Card>
  <Pager page={currentPage} totalPages={totalPages} total={patients.length} onChange={setPage}/>
  </div></AppLayout>;
}
