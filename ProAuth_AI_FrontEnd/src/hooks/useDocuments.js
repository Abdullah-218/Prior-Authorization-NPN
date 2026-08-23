import { useEffect, useState } from 'react';
import { documentsApi } from '../services/documentsApi';

// Real uploaded files live in the separate Document table (POST
// /api/documents), NOT in the Authorization row's own `documents` JSONB
// field — the doctor wizard's submission payload always sends
// `documents: []` (see submitAuthorizationPipeline.js), so that field is
// never actually populated for a real request. This hook is the real
// source: one GET /api/documents?authorizationId=X per request, fetched
// only for the authorization id(s) a page is actually showing — same
// cheap-list-vs-expensive-detail split as useTriageDetail, just extended
// to a small list of ids for pages that show a patient's full document
// history across several requests.
export function useDocumentsForAuthorizations(authorizationIds) {
  const key = (authorizationIds || []).filter(Boolean).join(',');
  const [documentsByAuthorization, setDocumentsByAuthorization] = useState({});
  const [status, setStatus] = useState('loading');

  useEffect(() => {
    const ids = key ? key.split(',') : [];
    if (!ids.length) {
      setDocumentsByAuthorization({});
      setStatus('done');
      return undefined;
    }
    let cancelled = false;
    setStatus('loading');
    Promise.all(ids.map(id => documentsApi.listForAuthorization(id).catch(() => [])))
      .then(results => {
        if (cancelled) return;
        const map = {};
        ids.forEach((id, index) => { map[id] = results[index]; });
        setDocumentsByAuthorization(map);
        setStatus('done');
      });
    return () => { cancelled = true; };
  }, [key]);

  return { documentsByAuthorization, status };
}

// Real Document rows -> the [name, status] tuple shape every documents
// card already renders. A row existing here means it was successfully
// uploaded — there's no separate "missing" concept at this level (that
// comes from the triage evaluation's documentEvidence.missingDocuments,
// a different real signal entirely, not the upload record).
export function mapDocumentsToTuples(documentRows) {
  return (documentRows || []).map(doc => [doc.fileName, 'Uploaded']);
}

// Real Document rows, trimmed to exactly what DocumentRow (2026-08-20+,
// document viewing) needs to render a row and fetch its file — id is what
// mapDocumentsToTuples' tuple shape above deliberately drops, since a
// "view this document" action needs a concrete id to call
// GET /api/documents/:id/file against.
export function mapDocumentsToRows(documentRows) {
  return (documentRows || []).map(doc => ({ id: doc.id, fileName: doc.fileName, mimeType: doc.mimeType, documentType: doc.documentType }));
}

