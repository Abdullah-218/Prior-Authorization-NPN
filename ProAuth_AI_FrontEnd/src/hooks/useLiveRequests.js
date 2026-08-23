import { useEffect, useState } from 'react';
import { loadRequests } from '../services/authorizationSync';

const DEFAULT_POLL_INTERVAL_MS = 20000;

// Triggers a real GET /api/authorizations fetch on mount, replacing the
// shared requests[] array in place. Returns {status, error} so a page can
// show a loading/error state — dashboardService/patientService calls made
// during the SAME render, after status flips to 'done', will read the
// now-real data (they read the shared array directly, not reactively).
//
// Live updates (2026-08-20+): also re-fetches on an interval so a nurse's
// approval, a doctor's new submission, etc. show up without a manual
// browser refresh — the same shared-array replace the initial load already
// does, just repeated. Every poll bumps internal state even when the data
// turns out unchanged, which is what actually forces the pages that call
// this hook to re-render and re-read the shared array (they read it
// directly during render, not via a subscription) — see data/requests.js.
// Paused while the tab is in the background (document.visibilityState) so
// an idle background tab doesn't keep firing requests. A failed poll
// (e.g. a transient network blip) is swallowed rather than surfaced as an
// error — the page keeps showing its last good data instead of flipping to
// an error state over a single missed tick; only the INITIAL load's
// failure is shown to the user.
export function useLiveRequests({ poll = true, intervalMs = DEFAULT_POLL_INTERVAL_MS } = {}) {
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState('');
  const [, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const fetchOnce = isInitial => {
      if (isInitial) setStatus('loading');
      return loadRequests()
        .then(() => {
          if (cancelled) return;
          setStatus('done');
          setError('');
          setTick(t => t + 1);
        })
        .catch(err => {
          if (cancelled) return;
          if (isInitial) { setError(err.message || 'Failed to load authorizations.'); setStatus('error'); }
        });
    };

    fetchOnce(true);
    if (!poll) return () => { cancelled = true; };

    const id = setInterval(() => {
      if (document.visibilityState === 'hidden') return;
      fetchOnce(false);
    }, intervalMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [poll, intervalMs]);

  return { status, error };
}
