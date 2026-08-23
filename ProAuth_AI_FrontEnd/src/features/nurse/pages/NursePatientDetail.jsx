import React, { useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { AlertTriangle, Check, ChevronLeft, ChevronRight, FileText, UploadCloud } from 'lucide-react';
import AppLayout from '../../../components/layout/AppLayout';
import { Badge, Card, DataState } from '../../../components/ui';
import { dashboardService } from '../../../services/dashboardService';
import { patientService } from '../../../services/patientService';
import { reviewApi } from '../../../services/reviewApi';
import { attachTriageResult, mapAuthorizationRowToRequest } from '../../../services/requestMapper';
import { upsertRequest } from '../../../data/requests';
import { useLiveRequests } from '../../../hooks/useLiveRequests';
import { usePriorityQueue } from '../../../hooks/usePriorityQueue';
import { useTriageDetail } from '../../../hooks/useTriageDetail';
import { useDocumentsForAuthorizations, mapDocumentsToRows } from '../../../hooks/useDocuments';
import AuthorizationDetail from '../../../components/authorization/AuthorizationDetail';
import { DocumentRow } from '../../../components/documents/DocumentRow';

const historyColumns = '.65fr .9fr .85fr 1.55fr .8fr .5fr .75fr .75fr .75fr .4fr';
const defaultTimeline = ['Submitted', 'Under review', 'Decision'];
const finalStatuses = ['Approved', 'Denied', 'Rejected'];
const TIER_TONE = { HIGH: 'red', MEDIUM: 'amber', LOW: 'blue' };
const TIER_LABEL = { HIGH: 'High risk', MEDIUM: 'Moderate risk', LOW: 'Low risk' };

export default function NursePatientDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { status: listStatus, error: listError } = useLiveRequests();
  const { priorityByAuthorization } = usePriorityQueue();
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState('');

  const { requests } = dashboardService.getNurseDashboard();
  const patient = listStatus === 'done' ? patientService.getPatientByIdFromList(requests, id) : null;
  const { evaluation, status: triageStatus } = useTriageDetail(patient?.latest?.id);
  const { documentsByAuthorization } = useDocumentsForAuthorizations(patient ? patient.requests.map(r => r.id) : []);

  if (listStatus !== 'done') return <AppLayout><div className="page simple"><DataState status={listStatus} error={listError}/></div></AppLayout>;
  if (!patient) return <Navigate to="/patients" replace/>;

  const latest = triageStatus === 'done' ? attachTriageResult(patient.latest, evaluation) : patient.latest;
  const priority = priorityByAuthorization[latest.id];
  // Every real Document row is shown — no dedup by filename. Two documents
  // can legitimately share a filename (e.g. the same test PDF uploaded for
  // both "clinical notes" and "lab reports") while being genuinely
  // distinct uploads with their own id/category; collapsing them by name
  // alone previously hid real submitted documents from the reviewer.
  const documents = patient.requests.flatMap(request => mapDocumentsToRows(documentsByAuthorization[request.id]).map(document => ({ document, request })));
  const timelineSteps = latest.timeline?.length ? latest.timeline : defaultTimeline;
  const currentIndex = finalStatuses.includes(latest.status) ? timelineSteps.length - 1 : Math.max(0, timelineSteps.length - 2);

  // Real PATCH /api/authorizations/:id/review — the response is the full,
  // updated Authorization row (status/reviewNote/reviewedBy/decisionSource
  // change; the JSONB clinical/treatment/etc. fields are untouched). It
  // does NOT include the triage evaluation, so resultDetail/confidence are
  // carried over from what was already loaded rather than dropped.
  const recordDecision = async decision => {
    setSubmitting(true);
    setActionError('');
    try {
      const updatedRow = await reviewApi.recordDecision(latest.id, decision, note);
      upsertRequest({ ...mapAuthorizationRowToRequest(updatedRow), resultDetail: latest.resultDetail, confidence: latest.confidence });
      navigate('/nurse/review');
    } catch (err) {
      setActionError(err.message || 'Could not record this decision.');
      setSubmitting(false);
    }
  };
  const handleApprove = () => recordDecision('Approved');
  const handleRequestInfo = () => recordDecision('Additional Information Required');

  return <AppLayout><div className="page simple">
    <a className="text-button" href="/patients"><ChevronLeft size={15}/>Back to Patients</a>
    <div className="page-heading"><div><p className="eyebrow">PATIENT REVIEW PROFILE</p><h1>{patient.patient}</h1><p>Clinical review context and request history.</p></div><Badge type="blue">{patient.activeRequests} request{patient.activeRequests === 1 ? '' : 's'}</Badge></div>

    <Card><div className="section-title"><div><p className="eyebrow">CLINICAL DECISION</p><h3>{latest.id} · {latest.service}</h3></div><div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>{priority?.priorityTier && <Badge type={TIER_TONE[priority.priorityTier] || 'blue'}>{TIER_LABEL[priority.priorityTier] || priority.priorityTier}</Badge>}<Badge type={latest.tone}>{latest.status}</Badge></div></div>
      {priority?.reasonCodes?.length > 0 && <div className="connected" style={{ marginTop: 4 }}><AlertTriangle size={16}/><span><strong>Why this priority</strong><small>{priority.reasonCodes.join(' · ')}</small></span></div>}
      <p className="body-copy">Review the patient details, AI analysis, and submitted documents below, then approve this request or send it back to the doctor for more information.</p>
      <label className="field textarea" style={{ marginTop: 14 }}><span>Reviewer note (optional)</span><textarea placeholder="Add context for the doctor — e.g. what evidence is missing…" value={note} onChange={e => setNote(e.target.value)}/></label>
      {actionError && <p className="missing"><AlertTriangle size={16}/><span>{actionError}</span></p>}
      <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
        <button className="button primary" type="button" disabled={submitting} onClick={handleApprove}><Check size={16}/>{submitting ? 'Saving…' : 'Approve'}</button>
        <button className="button" type="button" disabled={submitting} onClick={handleRequestInfo}><UploadCloud size={16}/>{submitting ? 'Saving…' : 'Request More Information'}</button>
      </div>
    </Card>

    <Card><div className="section-title"><div><p className="eyebrow">PATIENT OVERVIEW</p><h3>{patient.patient}</h3></div></div>
      <div className="policy-meta"><span><b>Patient ID</b>{patient.patientId}</span><span><b>Date of birth</b>{patient.dateOfBirth || 'Not provided'}</span><span><b>Age</b>{patient.age || 'Not provided'}</span><span><b>Sex</b>{patient.sex || 'Not provided'}</span></div>
      <div className="policy-meta"><span><b>Insurance provider</b>{patient.insuranceProvider || 'Not provided'}</span><span><b>Insurance plan</b>{patient.planName || 'Not provided'}</span><span><b>Member ID</b>{patient.memberId || 'Not provided'}</span></div>
    </Card>

    <Card><div className="section-title"><div><p className="eyebrow">CLINICAL SUMMARY</p><h3>Diagnosis & history</h3></div></div>
      <div className="policy-meta"><span><b>Primary diagnosis</b>{latest.diagnosis || 'Not specified'}</span><span><b>ICD-10</b>{latest.icd10 || 'Not provided'}</span><span><b>Secondary diagnoses</b>{latest.secondaryDiagnoses || 'None reported'}</span></div>
      <p className="body-copy">{latest.clinicalHistory || 'No clinical history documented for this request.'}</p>
      <p className="hint">Current medications, previous procedures, and clinical observations are not captured in this demo dataset.</p>
    </Card>

    <div className="section-title patient-section-label"><div><p className="eyebrow">AI & ML ANALYSIS</p><h3>What the doctor submitted</h3></div></div>
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
