import { Navigate, useParams } from 'react-router-dom';
import { ChevronRight, Download } from 'lucide-react';
import AppLayout from '../components/layout/AppLayout';
import { requests } from '../data/requests';
import { useLiveRequests } from '../hooks/useLiveRequests';
import { useTriageDetail } from '../hooks/useTriageDetail';
import { attachTriageResult } from '../services/requestMapper';
import { DataState } from '../components/ui';
import AuthorizationDetail from '../components/authorization/AuthorizationDetail';

// A fresh submission (Processing.jsx's pipeline) already upserts the full
// request — including resultDetail — into the shared requests[] array, so
// the common case never needs the fetches below. This page also has to
// survive a direct navigation or a page refresh though, where the array
// starts empty: useLiveRequests() repopulates the base row from a real
// GET /api/authorizations, and useTriageDetail() fills resultDetail in
// from a real GET /api/triage/evaluations/:id if it isn't already there.
export default function ResultPage() {
  const { id } = useParams();
  const { status: listStatus, error: listError } = useLiveRequests();
  const baseRequest = listStatus === 'done' ? requests.find(item => item.id === id) : null;
  const needsEvaluation = Boolean(baseRequest) && !baseRequest.resultDetail;
  const { evaluation, status: triageStatus } = useTriageDetail(needsEvaluation ? id : null);

  if (listStatus !== 'done') {
    return <AppLayout><div className="page result"><DataState status={listStatus} error={listError} /></div></AppLayout>;
  }
  if (!baseRequest) return <Navigate to="/dashboard" replace />;

  const request = needsEvaluation && triageStatus === 'done' ? attachTriageResult(baseRequest, evaluation) : baseRequest;
  if (!request.resultDetail) {
    return <AppLayout><div className="page result"><DataState status={needsEvaluation ? triageStatus : 'loading'} error="" /></div></AppLayout>;
  }

  return <AppLayout><div className="page result">
    <div className="crumb">Authorization queue <ChevronRight size={14} /><span> {request.id}</span></div>
    <div className="result-top">
      <div><p className="eyebrow">AI TRIAGE RECOMMENDATION</p><h1>Authorization <span>{request.id}</span></h1><p>{request.patient} · {request.service} · Submitted {request.date}</p></div>
      <div className="result-actions"><button className="button primary no-print" type="button" onClick={() => window.print()}><Download size={16}/>Export report</button><button className="button primary no-print">Open reviewer workspace <ChevronRight size={16} /></button></div>
    </div>
    <AuthorizationDetail request={request} />
  </div></AppLayout>;
}
