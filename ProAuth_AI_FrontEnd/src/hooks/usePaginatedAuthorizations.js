import { useEffect, useState } from 'react';
import { authorizationApi } from '../services/authorizationApi';
import { mapAuthorizationRowToRequest } from '../services/requestMapper';

const DEFAULT_PAGE_SIZE = 10;

// Real server-side pagination for the 3 list pages that used to render
// every matching row in one unbounded list (AuditTrail's event log,
// ReviewerRequests, Queue) — see authorizationApi.js's
// getAuthorizationsPage(). Deliberately independent of the shared
// requests[]/useLiveRequests() array those pages used to read from: that
// array exists to serve pages needing the FULL role-scoped dataset
// (dashboards, detail lookups by id) and isn't a fit for "give me page 3
// of the Approved+automated filter" — fetching one page directly here is
// simpler than bolting pagination onto that shared store.
export function usePaginatedAuthorizations({ status, decisionSource, pageSize = DEFAULT_PAGE_SIZE } = {}) {
  const [page, setPage] = useState(1);
  const [state, setState] = useState({ requests: [], total: 0, totalPages: 1, status: 'loading', error: '' });

  // Changing filters (e.g. switching the Automated/Manual/All tab) resets
  // back to page 1 — page 4 of a different filter's results isn't
  // meaningful.
  useEffect(() => { setPage(1); }, [status, decisionSource]);

  useEffect(() => {
    let cancelled = false;
    setState(prev => ({ ...prev, status: 'loading' }));
    authorizationApi.getAuthorizationsPage({ status, decisionSource, page, limit: pageSize })
      .then(({ rows, total, totalPages }) => {
        if (cancelled) return;
        setState({ requests: rows.map(mapAuthorizationRowToRequest), total, totalPages, status: 'done', error: '' });
      })
      .catch(err => {
        if (cancelled) return;
        setState(prev => ({ ...prev, status: 'error', error: err.message || 'Failed to load authorizations.' }));
      });
    return () => { cancelled = true; };
  }, [status, decisionSource, page, pageSize]);

  return { ...state, page, setPage };
}
