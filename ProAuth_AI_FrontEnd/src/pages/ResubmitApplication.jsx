import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { AlertTriangle, Check, ChevronLeft, FileText, Send, X } from 'lucide-react';
import AppLayout from '../components/layout/AppLayout';
import { Badge, Card, DataState } from '../components/ui';
import Processing from './Processing';
import { authorizationApi } from '../services/authorizationApi';
import { useTriageDetail } from '../hooks/useTriageDetail';
import { resubmitAuthorization } from '../services/resubmitAuthorizationPipeline';

const DOCUMENT_CATEGORIES = [
  ['clinicalNotes', 'Clinical notes'],
  ['labReports', 'Lab reports'],
  ['previousTreatmentRecords', 'Previous treatment records'],
  ['prescriptions', 'Prescriptions'],
  ['imagingReports', 'Imaging reports'],
];

export default function ResubmitApplication() {
  const { id } = useParams();
  const [authorization, setAuthorization] = useState(null);
  const [loadStatus, setLoadStatus] = useState('loading');
  const [loadError, setLoadError] = useState('');
  const [additionalNotes, setAdditionalNotes] = useState('');
  const [files, setFiles] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const { evaluation } = useTriageDetail(id);

  useEffect(() => {
    let cancelled = false;
    authorizationApi.getAuthorizationById(id)
      .then(row => { if (!cancelled) { setAuthorization(row); setLoadStatus('done'); } })
      .catch(err => { if (!cancelled) { setLoadError(err.message || 'Application not found.'); setLoadStatus('error'); } });
    return () => { cancelled = true; };
  }, [id]);

  const onFilesChange = (category, categoryFiles) => setFiles(prev => ({ ...prev, [category]: categoryFiles }));

  // Same animated evaluation screen a brand-new submission shows
  // (Processing.jsx, shared) instead of a static disabled-button label —
  // the resubmit call runs the exact same real 40-90+ second RAG+Agents+ML
  // pipeline as a new request, so it deserves the same "this is genuinely
  // working" feedback.
  if (submitting) return <Processing
    task={() => resubmitAuthorization({ authorization, additionalNotes, files })}
    eyebrow="RESUBMISSION FOR REVIEW"
    heading="Re-evaluating your request"
    lead="Your updated evidence is re-run through the full policy, clinical, and document evaluation — then converges on a recommendation. Real evaluations can take up to two minutes."
    errorEyebrow="RESUBMISSION FAILED"
    errorHeading="We couldn't complete this re-evaluation"
    errorBackHref={`/doctor/resubmit/${id}`}
    errorBackLabel="Back to resubmission"
    navigateTo={authorizationId => `/authorizations/${authorizationId}`}
  />;

  if (loadStatus !== 'done') return <AppLayout><div className="page simple"><DataState status={loadStatus} error={loadError}/></div></AppLayout>;

  const missingDocuments = evaluation?.documentEvidence?.missingDocuments || [];

  return <AppLayout><div className="page workflow">
    <a className="text-button" href="/doctor/requests/need-information"><ChevronLeft size={15}/>Back to my requests</a>
    <div className="workflow-head"><div><p className="eyebrow">RESUBMIT FOR REVIEW</p><h1>{id}</h1><p>Additional information was requested. Add what's needed below and resubmit — the AI pipeline re-evaluates automatically and can take up to two minutes.</p></div></div>

    <Card className="form-card">
      {authorization.reviewNote && <div className="connected warn" style={{ marginBottom: 20 }}><AlertTriangle size={16}/><span><strong>Reviewer note</strong><small>{authorization.reviewNote}</small></span></div>}
      {missingDocuments.length > 0 && <div className="connected warn" style={{ marginBottom: 20 }}><AlertTriangle size={16}/><span><strong>Missing from last evaluation</strong><small>{missingDocuments.join(', ')}</small></span></div>}

      <label className="field textarea"><span>Additional clinical justification</span><textarea placeholder="Add whatever detail addresses the reviewer's note — this is appended to your original justification, not a replacement for it." value={additionalNotes} onChange={e => setAdditionalNotes(e.target.value)}/></label>

      <div className="form-title" style={{ marginTop: 24 }}><div><h2 style={{ fontSize: 15 }}>Add supporting documents</h2></div></div>
      {DOCUMENT_CATEGORIES.map(([category, label]) => <label className="doc-row" key={category} style={{ cursor: 'pointer' }}>
        <div className="doc-icon"><FileText size={19}/></div>
        <div><strong>{label}</strong><small>PDF, DOCX, PNG, or JPG · Maximum file size 20 MB</small></div>
        {files[category]?.length ? <Badge type="green"><Check size={12}/>{files[category].length} file{files[category].length === 1 ? '' : 's'}</Badge> : <Badge type="amber">Not attached</Badge>}
        <input type="file" multiple accept=".pdf,.doc,.docx,.jpg,.jpeg,.png" style={{ display: 'none' }}
          onChange={e => onFilesChange(category, Array.from(e.target.files || []))}/>
        {files[category]?.length > 0 && <button type="button" onClick={e => { e.preventDefault(); onFilesChange(category, []); }}><X size={16}/></button>}
      </label>)}

      <div className="form-actions">
        <a className="button" href="/doctor/requests/need-information">Cancel</a>
        <button className="button primary" type="button" onClick={() => setSubmitting(true)}><Send size={16}/>Resubmit for review</button>
      </div>
    </Card>
  </div></AppLayout>;
}
