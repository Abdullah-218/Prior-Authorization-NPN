import { useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { AlertTriangle, Check, ChevronLeft, Download, FileText, ShieldOff, UploadCloud } from 'lucide-react';
import AppLayout from '../../../components/layout/AppLayout';
import { Badge, Card, DataState } from '../../../components/ui';
import { requests, upsertRequest } from '../../../data/requests';
import { useLiveRequests } from '../../../hooks/useLiveRequests';
import { useTriageDetail } from '../../../hooks/useTriageDetail';
import { useDocumentsForAuthorizations, mapDocumentsToRows } from '../../../hooks/useDocuments';
import { reviewApi } from '../../../services/reviewApi';
import { attachTriageResult, mapAuthorizationRowToRequest } from '../../../services/requestMapper';
import AuthorizationDetail from '../../../components/authorization/AuthorizationDetail';
import { DocumentRow } from '../../../components/documents/DocumentRow';

// Same robustness pattern as pages/ResultPage.jsx: the shared requests[]
// array may already have this row (arrived here from a list page in the
// same session) or may not (direct link, refresh) — fall back to a live
// fetch either way rather than assuming.
export default function ReviewerAuthorization() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { status: listStatus, error: listError } = useLiveRequests();
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState('');
  const [actionError, setActionError] = useState('');

  const baseRequest = listStatus === 'done' ? requests.find(item => item.id === id) : null;
  const needsEvaluation = Boolean(baseRequest) && !baseRequest.resultDetail;
  const { evaluation, status: triageStatus } = useTriageDetail(needsEvaluation ? id : null);
  const { documentsByAuthorization } = useDocumentsForAuthorizations([id]);

  if (listStatus !== 'done') return <AppLayout><div className="page result"><DataState status={listStatus} error={listError}/></div></AppLayout>;
  if (!baseRequest) return <Navigate to="/queue" replace/>;

  const request = needsEvaluation && triageStatus === 'done' ? attachTriageResult(baseRequest, evaluation) : baseRequest;
  const documents = mapDocumentsToRows(documentsByAuthorization[id]);
  const isFinal = request.status === 'Approved' || request.status === 'Denied' || request.status === 'Rejected';

  // Real PATCH /api/authorizations/:id/review — same contract and
  // response-merging strategy as NursePatientDetail.jsx's recordDecision,
  // except this role can also Deny (backend gates that to ADMIN only,
  // which is exactly this role).
  const recordDecision = async decision => {
    setSubmitting(decision);
    setActionError('');
    try {
      const updatedRow = await reviewApi.recordDecision(request.id, decision, note);
      upsertRequest({ ...mapAuthorizationRowToRequest(updatedRow), resultDetail: request.resultDetail, confidence: request.confidence });
      navigate('/queue');
    } catch (err) {
      setActionError(err.message || 'Could not record this decision.');
      setSubmitting('');
    }
  };

  return <AppLayout><div className="page result">
    <a className="text-button no-print" href="/queue"><ChevronLeft size={15}/>Back to queue</a>
    <div className="result-top">
      <div><p className="eyebrow">AUTHORIZATION REVIEW</p><h1>Authorization <span>{request.id}</span></h1><p>{request.patient} · {request.service} · Submitted {request.date}</p></div>
      <div className="result-actions"><button className="button primary no-print" type="button" onClick={() => window.print()}><Download size={16}/>Export report</button></div>
    </div>

    <Card><div className="section-title"><div><p className="eyebrow">REQUEST DETAILS</p><h3>{request.service}</h3></div><Badge type={request.tone}>{request.status}</Badge></div>
      <div className="policy-meta"><span><b>Request ID</b>{request.id}</span><span><b>Patient</b>{request.patient}</span><span><b>Diagnosis</b>{request.diagnosis}</span><span><b>Requested service</b>{request.service}</span><span><b>Policy</b>{request.policy || request.policyName || 'Not specified'}</span><span><b>AI recommendation</b>{request.prediction}</span><span><b>Confidence</b>{request.confidence || '—'}</span><span><b>Submitted date</b>{request.date}</span></div>
      {request.reviewedBy && <p className="hint">Last reviewer decision by {request.reviewedBy}{request.reviewNote ? ` — "${request.reviewNote}"` : ''}.</p>}
    </Card>

    <div className="section-title patient-section-label"><div><p className="eyebrow">AI & ML ANALYSIS</p><h3>What the pipeline evaluated</h3></div></div>
    {request.resultDetail ? <AuthorizationDetail request={request}/> : needsEvaluation && triageStatus === 'loading'
      ? <Card><DataState status="loading"/></Card>
      : <Card><p className="body-copy">AI triage detail is not available for this request yet.</p></Card>}

    <Card><div className="section-title"><div><p className="eyebrow">EVIDENCE</p><h3>Supporting documents</h3></div><FileText size={18}/></div>{documents.length ? documents.map(document => <DocumentRow key={document.id} document={document} subtitle={`${request.id} · ${request.patient}`}/>) : <p className="body-copy">No supporting documents are attached to this request.</p>}</Card>

    <Card className="no-print"><div className="section-title"><div><p className="eyebrow">REVIEWER DECISION</p><h3>Record a final decision</h3></div></div>
      {isFinal
        ? <p className="body-copy">This request already has a final decision ({request.status}) and can't be changed here.</p>
        : <>
          <p className="body-copy">Review the AI recommendation, evidence, and documents above, then record a final decision for this request.</p>
          <label className="field textarea" style={{ marginTop: 14 }}><span>Reviewer note (optional)</span><textarea placeholder="Add context — e.g. why this was approved, denied, or what's missing…" value={note} onChange={e => setNote(e.target.value)}/></label>
          {actionError && <p className="missing"><AlertTriangle size={16}/><span>{actionError}</span></p>}
          <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
            <button className="button primary" type="button" disabled={Boolean(submitting)} onClick={() => recordDecision('Approved')}><Check size={16}/>{submitting === 'Approved' ? 'Saving…' : 'Approve'}</button>
            <button className="button" type="button" disabled={Boolean(submitting)} onClick={() => recordDecision('Additional Information Required')}><UploadCloud size={16}/>{submitting === 'Additional Information Required' ? 'Saving…' : 'Request More Information'}</button>
            <button className="button danger" type="button" disabled={Boolean(submitting)} onClick={() => recordDecision('Denied')}><ShieldOff size={16}/>{submitting === 'Denied' ? 'Saving…' : 'Deny'}</button>
          </div>
        </>}
    </Card>
  </div></AppLayout>;
}
