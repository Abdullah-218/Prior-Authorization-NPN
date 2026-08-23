import React from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { Check, ChevronLeft, ChevronRight, Download, FileText } from 'lucide-react';
import AppLayout from '../../../components/layout/AppLayout';
import { Badge, Card, DataState } from '../../../components/ui';
import { useAuth } from '../../../hooks/useAuth';
import { useLiveRequests } from '../../../hooks/useLiveRequests';
import { useTriageDetail } from '../../../hooks/useTriageDetail';
import { useDocumentsForAuthorizations, mapDocumentsToRows } from '../../../hooks/useDocuments';
import { patientService } from '../../../services/patientService';
import { attachTriageResult } from '../../../services/requestMapper';
import AuthorizationDetail from '../../../components/authorization/AuthorizationDetail';
import { DocumentRow } from '../../../components/documents/DocumentRow';

const historyColumns = '.65fr .9fr .85fr 1.55fr .8fr .5fr .75fr .75fr .75fr .4fr';
const defaultTimeline = ['Submitted', 'Under review', 'Decision'];
const finalStatuses = ['Approved', 'Denied', 'Rejected'];

export default function DoctorPatientDetail() {
  const { user } = useAuth();
  const { patientId } = useParams();
  const navigate = useNavigate();
  const { status: listStatus, error: listError } = useLiveRequests();
  const patient = listStatus === 'done' ? patientService.getPatientById(user.id, patientId) : null;
  const { evaluation, status: triageStatus } = useTriageDetail(patient?.latest?.id);
  const { documentsByAuthorization } = useDocumentsForAuthorizations(patient ? patient.requests.map(r => r.id) : []);

  if (listStatus !== 'done') return <AppLayout><div className="page simple"><DataState status={listStatus} error={listError}/></div></AppLayout>;
  if (!patient) return <Navigate to="/doctor/patients" replace/>;

  const latest = triageStatus === 'done' ? attachTriageResult(patient.latest, evaluation) : patient.latest;
  // Every real Document row is shown — no dedup by filename. Two documents
  // can legitimately share a filename (e.g. the same test PDF uploaded for
  // both "clinical notes" and "lab reports") while being genuinely
  // distinct uploads with their own id/category; collapsing them by name
  // alone previously hid real submitted documents from the doctor.
  const documents = patient.requests.flatMap(request => mapDocumentsToRows(documentsByAuthorization[request.id]).map(document => ({ document, request })));
  const timelineSteps = latest.timeline?.length ? latest.timeline : defaultTimeline;
  const currentIndex = finalStatuses.includes(latest.status) ? timelineSteps.length - 1 : Math.max(0, timelineSteps.length - 2);

  return <AppLayout><div className="page simple">
    <a className="text-button no-print" href="/doctor/patients"><ChevronLeft size={15}/>Back to Patients</a>
    <div className="page-heading"><div><p className="eyebrow">PATIENT PROFILE</p><h1>{patient.patient}</h1><p>Authorization status and submitted request history.</p></div><div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><Badge type="blue">{patient.activeRequests} request{patient.activeRequests === 1 ? '' : 's'}</Badge><button className="button primary no-print" type="button" onClick={() => window.print()}><Download size={15}/>Export report</button></div></div>

    <Card><div className="section-title"><div><p className="eyebrow">PATIENT OVERVIEW</p><h3>{patient.patient}</h3></div><Badge type={patient.tone}>{patient.latestStatus}</Badge></div>
      <div className="policy-meta"><span><b>Patient ID</b>{patient.patientId}</span><span><b>Date of birth</b>{patient.dateOfBirth || 'Not provided'}</span><span><b>Age</b>{patient.age || 'Not provided'}</span><span><b>Sex</b>{patient.sex || 'Not provided'}</span></div>
      <div className="policy-meta"><span><b>Insurance provider</b>{patient.insuranceProvider || 'Not provided'}</span><span><b>Insurance plan</b>{patient.planName || 'Not provided'}</span><span><b>Member ID</b>{patient.memberId || 'Not provided'}</span></div>
    </Card>

    <Card><div className="section-title"><div><p className="eyebrow">CLINICAL SUMMARY</p><h3>Diagnosis & history</h3></div></div>
      <div className="policy-meta"><span><b>Primary diagnosis</b>{latest.diagnosis || 'Not specified'}</span><span><b>ICD-10</b>{latest.icd10 || 'Not provided'}</span><span><b>Secondary diagnoses</b>{latest.secondaryDiagnoses || 'None reported'}</span></div>
      <p className="body-copy">{latest.clinicalHistory || 'No clinical history documented for this request.'}</p>
      <p className="hint">Current medications, previous procedures, and clinical observations are not captured in this demo dataset.</p>
    </Card>

    <div className="section-title patient-section-label"><div><p className="eyebrow">LATEST AI RECOMMENDATION</p><h3>{latest.id} · {latest.service}</h3></div></div>
    {latest.resultDetail ? <AuthorizationDetail request={latest}/> : <Card><p className="body-copy">AI triage detail is not available for this request yet.</p></Card>}

    <Card className="auth-history-card"><div className="section-title"><div><p className="eyebrow">AUTHORIZATION HISTORY</p><h3>All submitted requests</h3></div><FileText size={18}/></div>
      <div className="request-table"><div className="thead" style={{ gridTemplateColumns: historyColumns }}><span>Request ID</span><span>Requested Service</span><span>Diagnosis</span><span>Policy</span><span>AI Recommendation</span><span>Confidence</span><span>Status</span><span>Submitted</span><span>Last Updated</span><span>Action</span></div>
        {patient.requests.map(request => <div className="trow" style={{ gridTemplateColumns: historyColumns }} key={request.id}><strong>{request.id}</strong><span>{request.service}</span><span>{request.diagnosis}</span><span>{request.policyName || request.policy || 'Not specified'}</span><span>{request.prediction || '—'}</span><span>{request.confidence || '—'}</span><Badge type={request.tone}>{request.status}</Badge><small>{request.date}</small><small>{request.lastUpdated || request.date}</small><button className="open" type="button" onClick={() => navigate(`/request/${request.id}`)}><ChevronRight size={17}/></button></div>)}
      </div>
    </Card>

    <Card><div className="section-title"><div><p className="eyebrow">DOCUMENTS</p><h3>Supporting documents</h3></div></div>
      {documents.length > 0 ? documents.map(({ document, request }) => <DocumentRow key={document.id} document={document} subtitle={request.id}/>) : <div className="empty"><FileText size={27}/><h3>No documents</h3><p>Documents attached to this patient's requests will appear here.</p></div>}
    </Card>

    <Card><div className="section-title"><div><p className="eyebrow">TIMELINE</p><h3>Latest request progress</h3></div></div>
      <div className="flow">{timelineSteps.map((step, index) => { const isDone = index < currentIndex || (finalStatuses.includes(latest.status) && index === currentIndex); const isCurrent = index === currentIndex && !isDone; return <React.Fragment key={step}><div className={`flow-step ${isDone ? 'done' : isCurrent ? 'current' : ''}`}><span>{isDone ? <Check size={14}/> : index + 1}</span><label>{step}</label></div>{index < timelineSteps.length - 1 && <div className={`flow-line ${index < currentIndex ? 'filled' : ''}`}/>}</React.Fragment>; })}</div>
    </Card>
  </div></AppLayout>;
}
