import { useState } from 'react';
import { Check, CircleHelp, Clock3, Download, ShieldOff, UserCheck, Zap } from 'lucide-react';
import AppLayout from '../components/layout/AppLayout';
import { Badge, Card, DataState, Pager } from '../components/ui';
import { dashboardService } from '../services/dashboardService';
import { useLiveRequests } from '../hooks/useLiveRequests';
import { usePaginatedAuthorizations } from '../hooks/usePaginatedAuthorizations';

const csvColumns = ['Request ID', 'Patient', 'Diagnosis', 'Service', 'AI Recommendation', 'Confidence', 'Status', 'Submitted'];

function toCsvRow(request) {
  return [request.id, request.patient, request.diagnosis, request.service, request.prediction || '', request.confidence || '', request.status, request.date];
}

function downloadCsv(filename, requestList) {
  const rows = [csvColumns, ...requestList.map(toCsvRow)];
  const csv = rows.map(row => row.map(cell => `"${String(cell ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function eventFor(request) {
  if (request.status === 'Denied' && request.decisionSource === 'MANUAL_REVIEWER') return { icon: UserCheck, tone: 'red', text: `Denied by reviewer${request.reviewNote ? ` · ${request.reviewNote}` : ''}` };
  if (request.approvalType === 'automated') return { icon: Zap, tone: 'green', text: `Automatically approved · ${request.confidence} confidence` };
  if (request.approvalType === 'manual') return { icon: UserCheck, tone: 'blue', text: `Manually approved by reviewer · ${request.confidence} confidence` };
  if (request.status === 'Additional Information Required') return { icon: CircleHelp, tone: 'amber', text: `Additional evidence requested from provider${request.reviewNote ? ` · ${request.reviewNote}` : ''}` };
  return { icon: Clock3, tone: 'blue', text: `AI triage recommended ${(request.prediction || 'review').toLowerCase()} · ${request.confidence || '—'} confidence` };
}

export default function AuditTrail() {
  // Export cards need the FULL filtered dataset (a CSV missing 9 of 10
  // pages would be a real bug) — kept on the existing full-fetch shared
  // array. The Event Log below is the actual unbounded-render problem, so
  // ONLY that section is switched to real server-side pagination.
  const { status: listStatus, error: listError } = useLiveRequests();
  const dashboard = dashboardService.getInsuranceDashboard();
  const [downloadState, setDownloadState] = useState({});
  const { requests: eventLogRequests, total: eventLogTotal, page, totalPages, status: pageStatus, error: pageError, setPage } = usePaginatedAuthorizations({});

  if (listStatus !== 'done') return <AppLayout><div className="page simple"><DataState status={listStatus} error={listError}/></div></AppLayout>;

  const categories = [
    { key: 'automated', label: 'Automated Approved', icon: Zap, tone: 'green', requests: dashboard.automatedApprovals, filename: 'automated-approved-requests.csv' },
    { key: 'manual', label: 'Manual Approval', icon: UserCheck, tone: 'blue', requests: dashboard.manualApprovals, filename: 'manual-approval-requests.csv' },
    { key: 'pending', label: 'Pending', icon: Clock3, tone: 'amber', requests: dashboard.pendingCases, filename: 'pending-requests.csv' },
    { key: 'denied', label: 'Denied', icon: ShieldOff, tone: 'red', requests: dashboard.deniedRequests, filename: 'denied-requests.csv' }
  ];

  const handleDownload = category => {
    setDownloadState(prev => ({ ...prev, [category.key]: 'preparing' }));
    setTimeout(() => {
      downloadCsv(category.filename, category.requests);
      setDownloadState(prev => ({ ...prev, [category.key]: 'done' }));
      setTimeout(() => setDownloadState(prev => ({ ...prev, [category.key]: 'idle' })), 1400);
    }, 650);
  };

  return <AppLayout><div className="page simple">
    <h1>Audit trail</h1>
    <p className="lead">A transparent event record for every authorization.</p>

    <Card><div className="section-title"><div><p className="eyebrow">EXPORT</p><h3>Download requests</h3></div></div>
      <p className="body-copy">Export authorization records grouped by decision pathway.</p>
      <div className="download-grid">{categories.map(category => {
        const state = downloadState[category.key] || 'idle';
        const Icon = category.icon;
        return <div className={`download-card ${state}`} key={category.key}>
          <div className={`download-icon ${category.tone}`}>
            {state === 'preparing' ? <span className="download-spinner"/> : state === 'done' ? <span className="download-check"><Check size={18}/></span> : <Icon size={18}/>}
          </div>
          <div className="download-body"><strong>{category.label}</strong><small>{category.requests.length} request{category.requests.length === 1 ? '' : 's'}</small></div>
          <button className="button compact" type="button" disabled={state !== 'idle'} onClick={() => handleDownload(category)}>
            {state === 'preparing' ? 'Preparing…' : state === 'done' ? 'Downloaded' : <><Download size={14}/>CSV</>}
          </button>
        </div>;
      })}</div>
    </Card>

    <Card><div className="section-title"><div><p className="eyebrow">EVENT LOG</p><h3>Authorization activity</h3></div><Badge type="blue">{eventLogTotal} events</Badge></div>
      {pageStatus !== 'done' ? <DataState status={pageStatus} error={pageError}/> : eventLogRequests.map(request => { const event = eventFor(request); const EventIcon = event.icon; return <div className="attention-row" key={request.id}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
          <div className={`mini-avatar ${event.tone}`}><EventIcon size={14}/></div>
          <div><strong>{request.id} · {request.patient}</strong><small>{event.text}</small></div>
        </div>
        <Badge type={request.tone}>{request.status}</Badge>
        <small>{request.lastUpdated || request.date}</small>
      </div>; })}
    </Card>
    <Pager page={page} totalPages={totalPages} total={eventLogTotal} onChange={setPage}/>
  </div></AppLayout>;
}
