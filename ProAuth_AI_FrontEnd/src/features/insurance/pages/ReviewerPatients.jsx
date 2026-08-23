import { useState } from 'react';
import { ChevronRight, Users } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import AppLayout from '../../../components/layout/AppLayout';
import { Badge, Card, DataState, Pager } from '../../../components/ui';
import { patientService } from '../../../services/patientService';
import { useLiveRequests } from '../../../hooks/useLiveRequests';

const PAGE_SIZE = 12;

// Patients here are DERIVED (grouped client-side from the already-loaded
// requests[] array, not a paginated API of their own) — so pagination is
// client-side slicing of an already-in-memory list, not a network
// concern. This is what fixes the page being fully, unboundedly
// scrollable once there are hundreds of patients on record.
export default function ReviewerPatients() {
  const navigate = useNavigate();
  const { status: listStatus, error: listError } = useLiveRequests();
  const [page, setPage] = useState(1);
  if (listStatus !== 'done') return <AppLayout><div className="page simple"><DataState status={listStatus} error={listError}/></div></AppLayout>;
  const patients = patientService.getAllPatients();
  const totalPages = Math.max(1, Math.ceil(patients.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const visiblePatients = patients.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  return <AppLayout>
<div className="page simple"><h1>Patients</h1><Card><div className="section-title"><div><p className="eyebrow">PATIENT OVERVIEW</p><h3>Patient authorization status</h3></div><Badge type="blue">{patients.length} patients</Badge></div><div className="request-table"><div className="thead" style={{gridTemplateColumns:'1fr 1.5fr 1.5fr .9fr 1.2fr 30px'}}><span>Patient ID</span><span>Patient</span><span>Diagnosis</span><span>Requests</span><span>Latest status</span><span>Action</span></div>{visiblePatients.map(patient => <button className="trow" style={{gridTemplateColumns:'1fr 1.5fr 1.5fr .9fr 1.2fr 30px', width:'100%', border:0, textAlign:'left', cursor:'pointer'}} type="button" key={patient.patientId} onClick={() => navigate(`/patients/${patient.patientId}`)}><strong>{patient.patientId}</strong><span>{patient.patient}</span><span>{patient.diagnosis}</span><span>{patient.activeRequests}</span><Badge type={patient.latestStatus === 'Approved' ? 'green' : patient.latestStatus === 'Denied' ? 'red' : patient.latestStatus === 'Additional Information Required' ? 'amber' : 'blue'}>{patient.latestStatus}</Badge><ChevronRight size={17}/></button>)}</div>{patients.length === 0 && <div className="empty"><Users size={27}/><h3>No patients available</h3><p>Patients connected to authorization requests will appear here.</p></div>}</Card>
<Pager page={currentPage} totalPages={totalPages} total={patients.length} onChange={setPage}/>
</div></AppLayout>;
}
