import { useEffect, useState } from 'react';
import { triageApi } from '../services/triageApi';

// Full triage detail (resultDetail) is only fetched for the ONE request a
// detail/result page is actually showing — see requestMapper.js's split
// between the cheap list mapping and this — avoiding an N+1 fetch across
// every row in a list view.
export function useTriageDetail(authorizationId) {
  const [evaluation, setEvaluation] = useState(null);
  const [status, setStatus] = useState('loading');

  useEffect(() => {
    if (!authorizationId) {
      setStatus('done');
      return undefined;
    }
    let cancelled = false;
    setStatus('loading');
    triageApi.getLatestEvaluation(authorizationId)
      .then(result => { if (!cancelled) { setEvaluation(result); setStatus('done'); } })
      // Fails soft — a missing/broken evaluation fetch shouldn't block the
      // rest of the page from rendering, it just means resultDetail stays null.
      .catch(() => { if (!cancelled) { setEvaluation(null); setStatus('done'); } });
    return () => { cancelled = true; };
  }, [authorizationId]);

  return { evaluation, status };
}
