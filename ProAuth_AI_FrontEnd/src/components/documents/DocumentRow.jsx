import { useState } from 'react';
import { AlertTriangle, Download, FileText, X } from 'lucide-react';
import { Badge } from '../ui';
import { documentsApi } from '../../services/documentsApi';

const DOCUMENT_TYPE_LABELS = {
  CLINICAL_NOTES: 'Clinical notes',
  PRESCRIPTION: 'Prescription',
  LAB_REPORTS: 'Lab reports',
  IMAGING_REPORT: 'Imaging report',
  PREVIOUS_TREATMENT_RECORDS: 'Previous treatment records',
};

// One uploaded document, with a real "View" action — GET
// /api/documents/:id/file is authenticated (needs the Authorization
// header), so this fetches it as a Blob and opens it in an inline modal
// rather than a plain <a href> (which can't attach that header at all).
// PDFs/images render directly; anything else falls back to a download
// link for the same blob.
export function DocumentRow({ document, subtitle }) {
  const [preview, setPreview] = useState(null); // { url, mimeType }
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const openDocument = async () => {
    setLoading(true);
    setError('');
    try {
      const blob = await documentsApi.getFileBlob(document.id);
      setPreview({ url: URL.createObjectURL(blob), mimeType: document.mimeType || blob.type });
    } catch (err) {
      setError(err.message || 'Could not open this document.');
    } finally {
      setLoading(false);
    }
  };

  const closePreview = () => {
    if (preview?.url) URL.revokeObjectURL(preview.url);
    setPreview(null);
  };

  return <>
    <div className="doc-row">
      <div className="doc-icon"><FileText size={19}/></div>
      <div><strong>{document.fileName}</strong><small>{DOCUMENT_TYPE_LABELS[document.documentType] || document.documentType || 'Document'}{subtitle ? ` · ${subtitle}` : ''}</small></div>
      <Badge type="green">Uploaded</Badge>
      <button className="button compact" type="button" disabled={loading} onClick={openDocument}>{loading ? 'Opening…' : 'View'}</button>
    </div>
    {error && <p className="missing" style={{ marginTop: -4 }}><AlertTriangle size={14}/><span>{error}</span></p>}
    {preview && <div className="doc-modal-overlay" role="dialog" aria-modal="true" onClick={closePreview}>
      <div className="doc-modal" onClick={event => event.stopPropagation()}>
        <div className="doc-modal-head"><strong>{document.fileName}</strong><button className="doc-modal-close" type="button" onClick={closePreview} aria-label="Close"><X size={18}/></button></div>
        <div className="doc-modal-body">
          {preview.mimeType?.startsWith('image/')
            ? <img src={preview.url} alt={document.fileName}/>
            : preview.mimeType === 'application/pdf'
              ? <iframe title={document.fileName} src={preview.url}/>
              : <div className="doc-modal-fallback">
                  <FileText size={32}/>
                  <p>Preview isn't available for this file type.</p>
                  <a className="button primary" href={preview.url} download={document.fileName}><Download size={15}/>Download {document.fileName}</a>
                </div>}
        </div>
      </div>
    </div>}
  </>;
}
