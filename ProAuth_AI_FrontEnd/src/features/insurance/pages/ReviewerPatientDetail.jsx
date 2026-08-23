import React, { useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { AlertTriangle, Check, ChevronLeft, ChevronRight, Download, FileText, ShieldOff, UploadCloud } from 'lucide-react';
import AppLayout from '../../../components/layout/AppLayout';
import { Badge, Card, DataState } from '../../../components/ui';
import { patientService } from '../../../services/patientService';
import { reviewApi } from '../../../services/reviewApi';
import { attachTriageResult, mapAuthorizationRowToRequest } from '../../../services/requestMapper';
import { upsertRequest } from '../../../data/requests';
import { useLiveRequests } from '../../../hooks/useLiveRequests';
import { useTriageDetail } from '../../../hooks/useTriageDetail';
import { useDocumentsForAuthorizations, mapDocumentsToRows } from '../../../hooks/useDocuments';
import AuthorizationDetail from '../../../components/authorization/AuthorizationDetail';
import { DocumentRow } from '../../../components/documents/DocumentRow';

const historyColumns = '.65fr .9fr .85fr 1.55fr .8fr .5fr .75fr .75fr .75fr .4fr';
const defaultTimeline = ['Submitted', 'Under review', 'Decision'];
const finalStatuses = ['Approved', 'Denied', 'Rejected'];

export default function ReviewerPatientDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { status: listStatus, error: listError } = useLiveRequests();
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState('');
  const [actionError, setActionError] = useState('');
  const patient = listStatus === 'done' ? patientService.getPatientByIdAnyOwner(id) : null;
  const { evaluation, status: triageStatus } = useTriageDetail(patient?.latest?.id);
  const { documentsByAuthorization } = useDocumentsForAuthorizations(patient ? patient.requests.map(r => r.id) : []);

  if (listStatus !== 'done') return <AppLayout><div className="page simple"><DataState status={listStatus} error={listError}/></div></AppLayout>;
  if (!patient) return <Navigate to="/patients" replace/>;

  const latest = triageStatus === 'done' ? attachTriageResult(patient.latest, evaluation) : patient.latest;
  const isFinal = finalStatuses.includes(latest.status);
  // Every real Document row is shown — no dedup by filename. Two documents
  // can legitimately share a filename (e.g. the same test PDF uploaded for
  // both "clinical notes" and "lab reports") while being genuinely
  // distinct uploads with their own id/category; collapsing them by name
  // alone previously hid real submitted documents from the reviewer.
  const documents = patient.requests.flatMap(request => mapDocumentsToRows(documentsByAuthorization[request.id]).map(document => ({ document, request })));
  const timelineSteps = latest.timeline?.length ? latest.timeline : defaultTimeline;
  const currentIndex = isFinal ? timelineSteps.length - 1 : Math.max(0, timelineSteps.length - 2);

  // Same real PATCH /api/authorizations/:id/review contract as
  // NursePatientDetail.jsx/ReviewerAuthorization.jsx — this role also keeps
  // Deny (backend gates that to ADMIN only, which is exactly this role),
  // so it's the insurance side's other real decision-making entry point,
  // not just the standalone /authorizations/:id page.
  const recordDecision = async decision => {
    setSubmitting(decision);
    setActionError('');
    try {
      const updatedRow = await reviewApi.recordDecision(latest.id, decision, note);
      upsertRequest({ ...mapAuthorizationRowToRequest(updatedRow), resultDetail: latest.resultDetail, confidence: latest.confidence });
      navigate('/queue');
    } catch (err) {
      setActionError(err.message || 'Could not record this decision.');
      setSubmitting('');
    }
  };

  return <AppLayout><div className="page simple">
    <a className="text-button no-print" href="/patients"><ChevronLeft size={15}/>Back to Patients</a>
    <div className="page-heading"><div><p className="eyebrow">PATIENT REVIEW PROFILE</p><h1>{patient.patient}</h1><p>Patient context and authorization requests under review.</p></div><div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><Badge type="blue">{patient.activeRequests} request{patient.activeRequests === 1 ? '' : 's'}</Badge><button className="button primary no-print" type="button" onClick={() => window.print()}><Download size={15}/>Export report</button></div></div>

    <Card className="no-print"><div className="section-title"><div><p className="eyebrow">REVIEWER DECISION</p><h3>{latest.id} · {latest.service}</h3></div><Badge type={latest.tone}>{latest.status}</Badge></div>
      {isFinal
        ? <p className="body-copy">This request already has a final decision ({latest.status}) and can't be changed here.</p>
        : <>
          <p className="body-copy">Review the patient details, AI analysis, and submitted documents below, then record a final decision for this request.</p>
          <label className="field textarea" style={{ marginTop: 14 }}><span>Reviewer note (optional)</span><textarea placeholder="Add context — e.g. why this was approved, denied, or what's missing…" value={note} onChange={e => setNote(e.target.value)}/></label>
          {actionError && <p className="missing"><AlertTriangle size={16}/><span>{actionError}</span></p>}
          <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
            <button className="button primary" type="button" disabled={Boolean(submitting)} onClick={() => recordDecision('Approved')}><Check size={16}/>{submitting === 'Approved' ? 'Saving…' : 'Approve'}</button>
            <button className="button" type="button" disabled={Boolean(submitting)} onClick={() => recordDecision('Additional Information Required')}><UploadCloud size={16}/>{submitting === 'Additional Information Required' ? 'Saving…' : 'Request More Information'}</button>
            <button className="button danger" type="button" disabled={Boolean(submitting)} onClick={() => recordDecision('Denied')}><ShieldOff size={16}/>{submitting === 'Denied' ? 'Saving…' : 'Deny'}</button>
          </div>
        </>}
    </Card>

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
      <div className="flow">{timelineSteps.map((step, index) => { const isDone = index < currentIndex || (isFinal && index === currentIndex); const isCurrent = index === currentIndex && !isDone; return <React.Fragment key={step}><div className={`flow-step ${isDone ? 'done' : isCurrent ? 'current' : ''}`}><span>{isDone ? <Check size={14}/> : index + 1}</span><label>{step}</label></div>{index < timelineSteps.length - 1 && <div className={`flow-line ${index < currentIndex ? 'filled' : ''}`}/>}</React.Fragment>; })}</div>
    </Card>
  </div></AppLayout>;
}
